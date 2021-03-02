from unittest import TestCase
import pytest

from samtranslator.model.api.api_generator import ApiGenerator


class TestApiGenerator(TestCase):
    kwargs = {
        "logical_id": "ServerlessApi",
        "cache_cluster_enabled": False,
        "cache_cluster_size": False,
        "variables": None,
        "depends_on": None,
        "definition_body": None,
        "definition_uri": None,
        "name": "api",
        "stage_name": "stage",
    }

    def test_lambda_auth_permission_not_created(self):
        authorizers = {
            "Authorizers": {"LambdaAuth": {"FunctionArn": "FUNCTION_ARN", "FunctionInvokeRole": "FUNCTION_INVOKE_ROLE"}}
        }
        generator = ApiGenerator(auth=authorizers, **self.kwargs)
        permissions = generator._construct_authorizer_lambda_permission()
        self.assertEqual(permissions, [])

    def test_lambda_auth_permission_created(self):
        authorizers = {"Authorizers": {"LambdaAuth": {"FunctionArn": "FUNCTION_ARN"}}}
        generator = ApiGenerator(auth=authorizers, **self.kwargs)
        permissions = generator._construct_authorizer_lambda_permission()
        self.assertEqual(len(permissions), 1)
