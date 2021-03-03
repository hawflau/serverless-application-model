from mock import patch, Mock
from parameterized import parameterized, param
from unittest import TestCase
import os, sys

from samtranslator.feature_toggle.feature_toggle import (
    FeatureToggle,
    FeatureToggleLocalConfigProvider,
    FeatureToggleAppConfigConfigProvider,
)

my_path = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, my_path + "/..")


class TestFeatureToggle(TestCase):
    @parameterized.expand(
        [
            param("feature-1", "beta", "default", False),
            param("feature-1", "beta", "us-west-2", True),
            param("feature-2", "beta", "us-west-2", False),  # because feature is missing
            param("feature-1", "beta", "us-east-1", False),  # because percentage-based enablement is configured
            param("feature-1", "alpha", "us-east-1", False),  # non-exist stage
        ]
    )
    def test_feature_toggle_with_local_provider_for_stage(self, feature_name, stage, region, expected):
        feature_toggle = FeatureToggle(
            FeatureToggleLocalConfigProvider(os.path.join(my_path, "input", "feature_toggle_config.json"))
        )
        self.assertEqual(feature_toggle.is_enabled_for_stage_in_region(feature_name, stage, region), expected)
        self.assertFalse(feature_toggle.is_enabled(feature_name))

    @parameterized.expand(
        [
            param("feature-1", "beta", "default", "123456789123", False),
            param("feature-1", "beta", "us-west-2", "123456789123", True),
            param("feature-2", "beta", "us-west-2", "123456789123", False),  # because feature is missing
            param("feature-1", "beta", "ap-south-1", "123456789124", False),  # because default is used
            param("feature-1", "beta", "us-east-1", "123456789109", True),
            param("feature-1", "beta", "us-east-1", "123456789123", False),  # account_id is not within defined %
            param("feature-1", "alpha", "us-east-1", "123456789123", False),  # non-exist stage
        ]
    )
    def test_feature_toggle_with_local_provider_for_account_id(self, feature_name, stage, region, account_id, expected):
        feature_toggle = FeatureToggle(
            FeatureToggleLocalConfigProvider(os.path.join(my_path, "input", "feature_toggle_config.json")),
            stage=stage,
            region=region,
            account_id=account_id,
        )
        self.assertEqual(
            feature_toggle.is_enabled_for_account_in_region(feature_name, stage, account_id, region), expected
        )
        self.assertEqual(feature_toggle.is_enabled(feature_name), expected)


class TestFeatureToggleAppConfig(TestCase):
    def setUp(self):
        self.content_stream_mock = Mock()
        self.content_stream_mock.read.return_value = b"""
            {
        "feature-1": {
            "beta": {
                "us-west-2": {"enabled": true},
                "us-east-1": {"enabled-%": 10},
                "default": {"enabled": false},
                "123456789123": {"us-west-2": {"enabled": true}, "default": {"enabled": false}}
            },
            "gamma": {
                "default": {"enabled": false},
                "123456789123": {"us-east-1": {"enabled": false}, "default": {"enabled": false}}
            },
            "prod": {"default": {"enabled": false}}
        }
    }
        """
        self.app_config_mock = Mock()
        self.app_config_mock.get_configuration.return_value = {"Content": self.content_stream_mock}

    @parameterized.expand(
        [
            param("feature-1", "beta", "default", False),
            param("feature-1", "beta", "us-west-2", True),
            param("feature-2", "beta", "us-west-2", False),  # because feature is missing
            param("feature-1", "beta", "us-east-1", False),  # because percentage-based enablement is configured
            param("feature-1", "alpha", "us-east-1", False),  # non-exist stage
        ]
    )
    @patch("samtranslator.feature_toggle.feature_toggle.boto3")
    def test_feature_toggle_for_stage(self, feature_name, stage, region, expected, boto3_mock):
        boto3_mock.client.return_value = self.app_config_mock
        feature_toggle_config_provider = FeatureToggleAppConfigConfigProvider(
            "test_app_id", "test_env_id", "test_conf_id"
        )
        feature_toggle = FeatureToggle(feature_toggle_config_provider)
        self.assertEqual(feature_toggle.is_enabled_for_stage_in_region(feature_name, stage, region), expected)

    @parameterized.expand(
        [
            param("feature-1", "beta", "default", "123456789123", False),
            param("feature-1", "beta", "us-west-2", "123456789123", True),
            param("feature-2", "beta", "us-west-2", "123456789123", False),  # because feature is missing
            param("feature-1", "beta", "ap-south-1", "123456789124", False),  # because default is used
            param("feature-1", "beta", "us-east-1", "123456789109", True),
            param("feature-1", "beta", "us-east-1", "123456789123", False),  # account_id is not within defined %
            param("feature-1", "alpha", "us-east-1", "123456789123", False),  # non-exist stage
        ]
    )
    @patch("samtranslator.feature_toggle.feature_toggle.boto3")
    def test_feature_toggle_for_account_id(self, feature_name, stage, region, account_id, expected, boto3_mock):
        boto3_mock.client.return_value = self.app_config_mock
        feature_toggle_config_provider = FeatureToggleAppConfigConfigProvider(
            "test_app_id", "test_env_id", "test_conf_id"
        )
        feature_toggle = FeatureToggle(
            feature_toggle_config_provider, stage=stage, region=region, account_id=account_id
        )
        self.assertEqual(
            feature_toggle.is_enabled_for_account_in_region(feature_name, stage, account_id, region), expected
        )
        self.assertEqual(feature_toggle.is_enabled(feature_name), expected)


class TestFeatureToggleAppConfigConfigProvider(TestCase):
    @patch("samtranslator.feature_toggle.feature_toggle.boto3")
    def test_feature_toggle_with_exception(self, boto3_mock):
        boto3_mock.client.raiseError.side_effect = Exception()
        feature_toggle_config_provider = FeatureToggleAppConfigConfigProvider(
            "test_app_id", "test_env_id", "test_conf_id"
        )
        self.assertEqual(feature_toggle_config_provider.config, {})
