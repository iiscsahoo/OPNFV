# Copyright 2015 Open Platform for NFV Project, Inc. and its contributors
# This software is distributed under the terms and conditions of the 'Apache-2.0'
# license which can be found in the file 'LICENSE' in this package distribution
# or at 'http://www.apache.org/licenses/LICENSE-2.0'.

import webob
import logging
import json
import six
import requests
import re
import httplib

from keystone import exception
from cStringIO import StringIO
from oslo_config import cfg
# from keystoneclient import auth
from keystonemiddleware.i18n import _, _LC, _LE, _LI, _LW


_OPTS = [
    cfg.StrOpt('auth_uri',
               default="http://127.0.0.1:35357/v3",
               help='Complete public Identity API endpoint.'),
    cfg.StrOpt('auth_version',
               default=None,
               help='API version of the admin Identity API endpoint.'),
    cfg.StrOpt('authz_login',
               default="admin",
               help='Name of the administrator who will connect to the Keystone Moon backends.'),
    cfg.StrOpt('authz_password',
               default="nomoresecrete",
               help='Password of the administrator who will connect to the Keystone Moon backends.'),
    cfg.StrOpt('logfile',
               default="/tmp/authz.log",
               help='File where logs goes.'),
    ]

_AUTHZ_GROUP = 'keystone_authz'
CONF = cfg.CONF
CONF.register_opts(_OPTS, group=_AUTHZ_GROUP)
CONF.debug = True
# auth.register_conf_options(CONF, _AUTHZ_GROUP)

# from http://developer.openstack.org/api-ref-objectstorage-v1.html
SWIFT_API = (
    ("^/v1/(?P<account>[\w_-]+)$", "GET", "get_account_details"),
    ("^/v1/(?P<account>[\w_-]+)$", "POST", "modify_account"),
    ("^/v1/(?P<account>[\w_-]+)$", "HEAD", "get_account"),
    ("^/v1/(?P<account>[\w_-]+)/(?P<container>[\w-]+)$", "GET", "get_container"),
    ("^/v1/(?P<account>[\w_-]+)/(?P<container>[\w-]+)$", "PUT", "create_container"),
    ("^/v1/(?P<account>[\w_-]+)/(?P<container>[\w-]+)$", "POST", "update_container_metadata"),
    ("^/v1/(?P<account>[\w_-]+)/(?P<container>[\w-]+)$", "DELETE", "delete_container"),
    ("^/v1/(?P<account>[\w_-]+)/(?P<container>[\w-]+)$", "HEAD", "get_container_metadata"),
    ("^/v1/(?P<account>[\w_-]+)/(?P<container>[\w-]+)/(?P<object>.+)$", "GET", "get_object"),
    ("^/v1/(?P<account>[\w_-]+)/(?P<container>[\w-]+)/(?P<object>.+)$", "PUT", "create_object"),
    ("^/v1/(?P<account>[\w_-]+)/(?P<container>[\w-]+)/(?P<object>.+)$", "COPY", "copy_object"),
    ("^/v1/(?P<account>[\w_-]+)/(?P<container>[\w-]+)/(?P<object>.+)$", "POST", "update_object_metadata"),
    ("^/v1/(?P<account>[\w_-]+)/(?P<container>[\w-]+)/(?P<object>.+)$", "DELETE", "delete_object"),
    ("^/v1/(?P<account>[\w_-]+)/(?P<container>[\w-]+)/(?P<object>.+)$", "HEAD", "get_object_metadata"),
)


class ServiceError(Exception):
    pass


class AuthZProtocol(object):
    """Middleware that handles authenticating client calls."""

    def __init__(self, app, conf):
        self._LOG = logging.getLogger(conf.get('log_name', __name__))
        # FIXME: events are duplicated in log file
        authz_fh = logging.FileHandler(CONF.keystone_authz["logfile"])
        self._LOG.setLevel(logging.DEBUG)
        self._LOG.addHandler(authz_fh)
        self._LOG.info(_LI('Starting Keystone authz middleware'))
        self._conf = conf
        self._app = app

        # MOON
        self.auth_host = conf.get('auth_host', "127.0.0.1")
        self.auth_port = int(conf.get('auth_port', 35357))
        auth_protocol = conf.get('auth_protocol', 'http')
        self._request_uri = '%s://%s:%s' % (auth_protocol, self.auth_host,
                                            self.auth_port)

        # SSL
        insecure = conf.get('insecure', False)
        cert_file = conf.get('certfile')
        key_file = conf.get('keyfile')

        if insecure:
            self._verify = False
        elif cert_file and key_file:
            self._verify = (cert_file, key_file)
        elif cert_file:
            self._verify = cert_file
        else:
            self._verify = None

    def get_url(self, url):
        conn = httplib.HTTPConnection(self.auth_host, self.auth_port)
        headers = {
            "Content-type": "application/x-www-form-urlencoded",
            "Accept": "text/plain,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        conn.request('GET', url, headers=headers)
        resp = conn.getresponse()
        content = resp.read()
        conn.close()
        try:
            return json.loads(content)
        except ValueError:
            return {"content": content}

    def _deny_request(self, code):
        error_table = {
            'AccessDenied': (401, 'Access denied'),
            'InvalidURI': (400, 'Could not parse the specified URI'),
            'NotFound': (404, 'URI not found'),
            'Error': (500, 'Server error'),
        }
        resp = webob.Response(content_type='text/xml')
        resp.status = error_table[code][0]
        error_msg = ('<?xml version="1.0" encoding="UTF-8"?>\r\n'
                     '<Error>\r\n  <Code>%s</Code>\r\n  '
                     '<Message>%s</Message>\r\n</Error>\r\n' %
                     (code, error_table[code][1]))
        if six.PY3:
            error_msg = error_msg.encode()
        resp.body = error_msg
        return resp

    def _get_authz_from_moon(self, tenant_id, subject_id, object_id, action_id):
        try:
            _url ='{}/v3/OS-MOON/authz/{}/{}/{}/{}'.format(
                                        self._request_uri,
                                        tenant_id,
                                        subject_id,
                                        object_id,
                                        action_id)
            self._LOG.info(_url)
            response = requests.get(_url,verify=self._verify)
        except requests.exceptions.RequestException as e:
            self._LOG.error(_LI('HTTP connection exception: %s'), e)
            resp = self._deny_request('InvalidURI')
            raise ServiceError(resp)

        if response.status_code < 200 or response.status_code >= 300:
            self._LOG.debug('Keystone reply error: status=%s reason=%s',
                               response.status_code, response.reason)
            if response.status_code == 404:
                resp = self._deny_request('NotFound')
            elif response.status_code == 401:
                resp = self._deny_request('AccessDenied')
            else:
                resp = self._deny_request('Error')
            raise ServiceError(resp)

        return response

    def _find_openstack_component(self, env):
        if "nova.context" in env.keys():
            return "nova"
        elif "swift.authorize" in env.keys():
            return "swift"
        else:
            self._LOG.debug(env.keys())
            return "unknown"

    def _get_action(self, env, component):
        """ Find and return the action of the request
        Actually, find only Nova (start, destroy, pause, unpause, ...) and swift actions

        :param env: the request
        :return: the action or ""
        """
        action = ""
        self.input = ""
        if component == "nova":
            length = int(env.get('CONTENT_LENGTH', '0'))
            # TODO (dthom): compute for Nova, Cinder, Neutron, ...
            action = ""
            if length > 0:
                try:
                    sub_action_object = env['wsgi.input'].read(length)
                    self.input = sub_action_object
                    action = json.loads(sub_action_object).keys()[0]
                    body = StringIO(sub_action_object)
                    env['wsgi.input'] = body
                except ValueError:
                    self._LOG.error("Error in decoding sub-action")
                except Exception as e:
                    self._LOG.error(str(e))
            if not action or len(action) == 0 and "servers/detail" in env["PATH_INFO"]:
                return "list"
        if component == "swift":
            path = env["PATH_INFO"]
            method = env["REQUEST_METHOD"]
            for api in SWIFT_API:
                if re.match(api[0], path) and method == api[1]:
                    action = api[2]
            length = int(env.get('CONTENT_LENGTH', '0'))
            # TODO (dthom): compute for Nova, Cinder, Neutron, ...
            _action = ""
            if length > 0:
                try:
                    sub_action_object = env['wsgi.input'].read(length)
                    self.input = sub_action_object
                    _action = json.loads(sub_action_object).keys()[0]
                    body = StringIO(sub_action_object)
                    env['wsgi.input'] = body
                    self._LOG.debug("wsgi.input={}".format(_action))
                except ValueError:
                    self._LOG.error("Error in decoding sub-action")
                except Exception as e:
                    self._LOG.error(str(e))
        return action

    @staticmethod
    def _get_object(env, component):
        if component == "nova":
            # http://developer.openstack.org/api-ref-compute-v2.1.html
            # nova URLs:
            #    /<tenant_id>/servers/<server_id>
            #       list details for server_id
            #    /<tenant_id>/servers/<server_id>/action
            #       execute action to server_id
            #    /<tenant_id>/servers/<server_id>/metadata
            #       show metadata from server_id
            #    /<tenant_id>/servers/details
            #       list servers
            url = env.get("PATH_INFO").split("/")
            if url[-1] == "detail":
                return "servers"
            try:
                return url[3]
            except IndexError:
                return
        elif component == "swift":
            # remove the "/v1/" part of the URL
            return env.get("PATH_INFO").split("/", 2)[-1].replace("/", "-").replace(".", "-")
        return "unknown"

    def __call__(self, env, start_response):
        req = webob.Request(env)

        subject_id = env.get("HTTP_X_USER_ID")
        if not subject_id:
            self._LOG.warning("No subject_id found for {}".format(env.get("PATH_INFO")))
            return self._app(env, start_response)
        tenant_id = env.get("HTTP_X_TENANT_ID")
        if not tenant_id:
            self._LOG.warning("No tenant_id found for {}".format(env.get("PATH_INFO")))
            return self._app(env, start_response)
        component = self._find_openstack_component(env)
        action_id = self._get_action(env, component)
        self._LOG.debug("\033[1m\033[31mrequest={}\033[m".format(env["PATH_INFO"]))
        if action_id:
            object_id = self._get_object(env, component)
            if not object_id:
                object_id = "servers"
            self._LOG.debug("object_id={}".format(object_id))
            resp = self._get_authz_from_moon(tenant_id, subject_id, object_id, action_id)
            if resp.status_code == 200:
                answer = json.loads(resp.content)
                self._LOG.debug("action_id={}/{}".format(component, action_id))
                self._LOG.debug(answer)
                if "authz" in answer and answer["authz"]:
                    return self._app(env, start_response)
                self._LOG.error("You are not authorized to do that! ({})".format(unicode(answer["comment"])))
                raise exception.Unauthorized(message="You are not authorized to do that! ({})".format(unicode(answer["comment"])))
            else:
                self._LOG.error("Unable to request Moon ({}: {})".format(resp.status_code, resp.reason))
        else:
            self._LOG.debug("No action_id found for {}".format(env.get("PATH_INFO")))
            # If action is not found, we can't raise an exception because a lots of action is missing
            # in function self._get_action, it is not possible to get them all.
        return self._app(env, start_response)
        # raise exception.Unauthorized(message="You are not authorized to do that!")


def filter_factory(global_conf, **local_conf):
    """Returns a WSGI filter app for use with paste.deploy."""
    conf = global_conf.copy()
    conf.update(local_conf)

    def auth_filter(app):
        return AuthZProtocol(app, conf)
    return auth_filter

