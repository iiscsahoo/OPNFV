# Copyright 2015 Open Platform for NFV Project, Inc. and its contributors
# This software is distributed under the terms and conditions of the 'Apache-2.0'
# license which can be found in the file 'LICENSE' in this package distribution
# or at 'http://www.apache.org/licenses/LICENSE-2.0'.
import uuid

USER = {
    'name': 'admin',
    'domain_id': "default",
    'password': 'admin'
}
IE = {
    "name": "test IE",
    "policymodel": "policy_authz",
    "description": "a simple description."
}


def create_intra_extension(self, policy_model="policy_authz"):

    IE["model"] = policy_model
    IE["name"] = uuid.uuid4().hex
    genre = "admin"
    if "authz" in policy_model:
        genre = "authz"
    IE["genre"] = genre
    ref = self.admin_api.load_intra_extension_dict(self.root_api.root_admin_id,
                                                   intra_extension_dict=IE)
    self.admin_api.populate_default_data(ref)
    self.assertIsInstance(ref, dict)
    return ref


def create_user(self, username="TestAdminIntraExtensionManagerUser"):
    user = {
        "id": uuid.uuid4().hex,
        "name": username,
        "enabled": True,
        "description": "",
        "domain_id": "default"
    }
    _user = self.identity_api.create_user(user)
    return _user


def create_mapping(self, tenant_name=None, authz_id=None, admin_id=None):

    if not tenant_name:
        tenant_name = uuid.uuid4().hex

    tenant = {
        "id": uuid.uuid4().hex,
        "name": tenant_name,
        "description": uuid.uuid4().hex,
        "intra_authz_extension_id": authz_id,
        "intra_admin_extension_id": admin_id,
        "enabled": True,
        "domain_id": "default"
    }
    keystone_tenant = self.resource_api.create_project(tenant["id"], tenant)
    mapping = self.tenant_api.add_tenant_dict(self.root_api.root_admin_id, tenant["id"], tenant)
    self.assertIsInstance(mapping, dict)
    self.assertIn("intra_authz_extension_id", mapping[tenant["id"]])
    self.assertIn("intra_admin_extension_id", mapping[tenant["id"]])
    self.assertEqual(mapping[tenant["id"]]["intra_authz_extension_id"], authz_id)
    self.assertEqual(mapping[tenant["id"]]["intra_admin_extension_id"], admin_id)
    return tenant, mapping
