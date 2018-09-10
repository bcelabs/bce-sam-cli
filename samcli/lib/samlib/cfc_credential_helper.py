# coding=utf-8

import os
import ConfigParser

from baidubce.auth.bce_credentials import BceCredentials
from samcli.commands.exceptions import UserException

user_home = os.environ['HOME']
default_config_location = user_home + "/.bce/"
default_config_file = default_config_location + "config"
default_credential_file = default_config_location + "credentials"


def get_credentials():
    if not os.path.exists(default_credential_file):
        raise UserException("credential file not found : {} does not exist".format(default_credential_file))
    #生成config对象
    conf = ConfigParser.ConfigParser()
    #用config对象读取配置文件
    conf.read(default_credential_file)
    #指定section，option读取值
    ak = conf.get("default", "bce_access_key_id")
    sk = conf.get("default", "bce_secret_access_key")
    return BceCredentials(ak,sk)


def get_region():
    if not os.path.exists(default_credential_file):
        raise UserException("credential file not found : {} does not exist".format(default_config_file))
    #生成config对象
    conf = ConfigParser.ConfigParser()
    #用config对象读取配置文件
    conf.read(default_config_file)
    #指定section，option读取值
    return conf.get("default", "region")