import os
import sys
import json
import boto3
import logging

from botocore.config import Config

my_path = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, my_path + "/..")

LOG = logging.getLogger(__name__)


class FeatureToggle:
    """
    FeatureToggle is the class which will provide methods to query and decide if a feature is enabled based on where
    SAM is executing or not.
    """

    def __init__(self, config_provider, stage, account_id, region):
        self.feature_config = config_provider.config
        self.stage = stage
        self.account_id = account_id
        self.region = region

    def is_enabled(self, feature_name):
        """
        To check if feature is available

        :param feature_name: name of feature
        """
        if feature_name not in self.feature_config:
            LOG.warning("Feature '{}' not available in Feature Toggle Config.".format(feature_name))
            return False

        stage = self.stage
        region = self.region
        account_id = self.account_id
        if not stage or not region or not account_id:
            LOG.warning("One or more of stage, region and account_id is not properly set. Feature not enabled.")
            return False

        stage_config = self.feature_config.get(feature_name, {}).get(stage, {})
        if not stage_config:
            LOG.info("Stage '{}' not enabled for Feature '{}'.".format(stage, feature_name))
            return False

        if account_id in stage_config:
            account_config = stage_config[account_id]
            region_config = account_config[region] if region in account_config else account_config.get("default", {})
        else:
            region_config = stage_config[region] if region in stage_config else stage_config.get("default", {})

        if "enabled-%" in region_config:
            # Percentage-based enablement
            # Assumption: account_id is uniformly distributed
            # account_id is calculated into one of 100 partitions (0-99)
            # if partition < enabled_percent, we consider the feature is enabled for this given account_id
            enabled_percent = region_config["enabled-%"]
            partition = int(account_id) % 100
            is_enabled = partition < enabled_percent
        else:
            is_enabled = region_config.get("enabled", False)

        LOG.info("Feature '{}' is enabled: '{}'".format(feature_name, is_enabled))
        return is_enabled


class FeatureToggleConfigProvider:
    """Interface for all FeatureToggle config providers"""

    def __init__(self):
        pass

    @property
    def config(self):
        raise NotImplementedError


class FeatureToggleDefaultConfigProvider(FeatureToggleConfigProvider):
    """Default config provider, always return False for every query."""

    def __init__(self):
        FeatureToggleConfigProvider.__init__(self)

    @property
    def config(self):
        return {}


class FeatureToggleLocalConfigProvider(FeatureToggleConfigProvider):
    """Feature toggle config provider which uses a local file. This is to facilitate local testing."""

    def __init__(self, local_config_path):
        FeatureToggleConfigProvider.__init__(self)
        with open(local_config_path, "r") as f:
            config_json = f.read()
        self.feature_toggle_config = json.loads(config_json)

    @property
    def config(self):
        return self.feature_toggle_config


class FeatureToggleAppConfigConfigProvider(FeatureToggleConfigProvider):
    """Feature toggle config provider which loads config from AppConfig."""

    def __init__(self, application_id, environment_id, configuration_profile_id):
        FeatureToggleConfigProvider.__init__(self)
        try:
            LOG.info("Loading feature toggle config from AppConfig...")
            # Lambda function has 120 seconds limit
            # (5 + 25) * 2, 60 seconds maximum timeout duration
            client_config = Config(connect_timeout=5, read_timeout=25, retries={"total_max_attempts": 2})
            self.app_config_client = boto3.client("appconfig", config=client_config)
            response = self.app_config_client.get_configuration(
                Application=application_id,
                Environment=environment_id,
                Configuration=configuration_profile_id,
                ClientId="FeatureToggleAppConfigConfigProvider",
            )
            binary_config_string = response["Content"].read()
            self.feature_toggle_config = json.loads(binary_config_string.decode("utf-8"))
            LOG.info("Finished loading feature toggle config from AppConfig.")
        except Exception as ex:
            LOG.error("Failed to load config from AppConfig: {}. Using empty config.".format(ex))
            # There is chance that AppConfig is not available in a particular region.
            self.feature_toggle_config = json.loads("{}")

    @property
    def config(self):
        return self.feature_toggle_config
