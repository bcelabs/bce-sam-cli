import logging
import platform
import subprocess
import sys
import time
import base64
import os
import zipfile

from baidubce.services.cfc.cfc_client import CfcClient
from baidubce.exception import BceServerError
from baidubce.exception import BceHttpClientError
import cfc_deploy_conf

from samcli.commands.exceptions import UserException
from samcli.local.lambdafn.exceptions import FunctionNotFound
from samcli.commands.validate.lib.exceptions import InvalidSamDocumentException
from samcli.lib.samlib.cfc_credential_helper import get_region

from deploy_context import DeployContext
from user_exceptions import DeployContextException

LOG = logging.getLogger(__name__)
_TEMPLATE_OPTION_DEFAULT_VALUE = "template.yaml"


def execute_pkg_command_backup(command, args):
    LOG.debug("%s command is called", command)
    try:
        pkg_cmd = 'zip' if platform.system().lower() != 'windows' else 'rar'       
        cmd_option = "-r" if platform.system().lower() != 'windows' else 'r'
        subprocess.check_call([pkg_cmd, cmd_option, ] + list(args))
        LOG.debug("%s command successful", command)
    except subprocess.CalledProcessError as e:
        LOG.debug("Exception: %s", e)
        sys.exit(e.returncode)


def execute_pkg_command(command):
    LOG.debug("%s command is called", command)
    try:
        with DeployContext(template_file=_TEMPLATE_OPTION_DEFAULT_VALUE,
                           function_identifier=None,
                           env_vars_file=None,
                           log_file=None,
                           ) as context:
            for f in context.all_functions:
                _zip_up(f.codeuri, f.name)
    except FunctionNotFound:
        raise UserException("Function not found in template")
    except InvalidSamDocumentException as ex:
        raise UserException(str(ex))   


def execute_deploy_command(command):
    LOG.debug("%s command is called", command)
    try:
        with DeployContext(template_file=_TEMPLATE_OPTION_DEFAULT_VALUE,
                           function_identifier=None,
                           env_vars_file=None,
                           log_file=None,
                           ) as context:
            for f in context.all_functions:
                _do_deploy(f)

    except FunctionNotFound:
        raise UserException("Function not found in template")
    except InvalidSamDocumentException as ex:
        raise UserException(str(ex))   


def _do_deploy(function):
    # create a cfc client
    cfc_client = CfcClient(cfc_deploy_conf.get_config())
    existed = _check_if_exist(cfc_client, function.name)
    if existed:
        _update_function(cfc_client, function)
    else:
        _create_function(cfc_client, function)


def _check_if_exist(cfc_client, function_name):
    try:
        get_function_response = cfc_client.get_function(function_name)
        LOG.debug("[Sample CFC] get_function response:%s", get_function_response)
    except (BceServerError,BceHttpClientError) as e:#TODO 区分一下具体的异常,input out put 一致
        return False
    
    if (get_function_response.FunctionName == None or get_function_response.FunctionName != function_name):
        return False

    return True


def _create_function(cfc_client, function):
    # create a cfc function
    function_name = function.name
    base64_file = _get_function_base64_file(function_name)
    user_memorysize = function.memory if function.memory != None else 128
    user_timeout = function.timeout if function.timeout != None else 3
    user_runtime = _deal_with_func_runtime(function.runtime)
    user_region = get_region()
    
    create_response = cfc_client.create_function(function_name,
                                                 description="cfc function from bsam cli",
                                                 handler=function.handler,
                                                 memory_size=user_memorysize,
                                                 region=user_region,
                                                 zip_file=base64_file,
                                                 publish=False,
                                                 run_time=user_runtime,
                                                 timeout=user_timeout,
                                                 dry_run=False)   
    LOG.debug("[Sample CFC] create_response:%s", create_response)
    print("Function Create Response : ",create_response)

def _update_function(cfc_client, function):
    # update function code
    function_name = function.name
    base64_file = _get_function_base64_file(function)
    update_function_code_response = cfc_client.update_function_code(function_name,
                                                                    zip_file=base64_file,
                                                                    publish=True)
    LOG.debug("[Sample CFC] update_function_code_response:%s", update_function_code_response)
    print("Function Update Response : ",update_function_code_response)

def _get_function_base64_file(function_name):
    zipfile_name = function_name + '.zip'
    if not os.path.exists(zipfile_name):
            raise DeployContextException("Zip file not found : {}".format(zipfile_name))

    with open(zipfile_name, 'r') as fp:
        try:
            return base64.b64encode(fp.read())
        except ValueError as ex:
            raise DeployContextException("Failed to convert zipfile to base64: {}".format(str(ex)))


def _zip_up(startdir, file_news=None):
    if startdir == None:
        raise DeployContextException("Missing the file or the directory to zip up : {} is not valid".format(startdir))

    if file_news == None:
        file_news = startdir +'.zip' # 压缩后文件夹的名字 
    else:
        file_news = file_news + '.zip'
        
    z = zipfile.ZipFile(file_news,'w',zipfile.ZIP_DEFLATED) #参数一：文件夹名
    for dirpath, dirnames, filenames in os.walk(startdir):
        fpath = dirpath.replace(startdir,'') #这一句很重要，不replace的话，就从根目录开始复制
        fpath = fpath and fpath + os.sep or ''
        for filename in filenames:
            z.write(os.path.join(dirpath, filename),fpath+filename)
            print('%s , zip suceeded!'%(filename))
    z.close()
    

def _deal_with_func_runtime(function_runtime):
    if function_runtime in ('python','python2','python2.7'):
        return 'python2'
    if function_runtime in ('nodejs','nodejs6','nodejs6.11'):
        return 'nodejs6.11'
    else:
        raise UserException("Function runtime not supported")
