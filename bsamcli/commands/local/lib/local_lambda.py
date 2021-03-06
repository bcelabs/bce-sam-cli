"""
Implementation of Local Lambda runner
"""

import os
import logging
import boto3

from bsamcli.lib.samlib.cfc_credential_helper import get_credentials

from bsamcli.local.lambdafn.env_vars import EnvironmentVariables
from bsamcli.local.lambdafn.config import FunctionConfig
from bsamcli.local.lambdafn.exceptions import FunctionNotFound

LOG = logging.getLogger(__name__)


class LocalLambdaRunner(object):
    """
    Runs Lambda functions locally. This class is a wrapper around the `samcli.local` library which takes care
    of actually running the function on a Docker container.
    """
    PRESENT_DIR = "."
    MAX_DEBUG_TIMEOUT = 36000  # 10 hours in seconds

    def __init__(self,
                 local_runtime,
                 function_provider,
                 cwd,
                 env_vars_values=None,
                 aws_profile=None,
                 debug_context=None,
                 aws_region=None,
                 is_installing=None):
        """
        Initializes the class

        :param samcli.local.lambdafn.runtime.LambdaRuntime local_runtime: Lambda runtime capable of running a function
        :param samcli.commands.local.lib.provider.FunctionProvider function_provider: Provider that can return a
            Lambda function
        :param string cwd: Current working directory. We will resolve all function CodeURIs relative to this directory.
        :param dict env_vars_values: Optional. Dictionary containing values of environment variables
        :param integer debug_port: Optional. Port to bind the debugger to
        :param string debug_args: Optional. Additional arguments passed to the debugger
        :param string aws_profile: Optional. AWS Credentials profile to use
        :param string aws_region: Optional. AWS region to use
        """

        self.local_runtime = local_runtime
        self.provider = function_provider
        self.cwd = cwd
        self.env_vars_values = env_vars_values or {}
        self.aws_profile = aws_profile
        self.aws_region = aws_region
        self.debug_context = debug_context

    def invoke(self, function_name, event, is_installing=None, stdout=None, stderr=None):
        """
        Find the Lambda function with given name and invoke it. Pass the given event to the function and return
        response through the given streams.

        This function will block until either the function completes or times out.

        :param string function_name: Name of the Lambda function to invoke
        :param string event: Event data passed to the function. Must be a valid JSON String.
        :param io.BaseIO stdout: Stream to write the output of the Lambda function to.
        :param io.BaseIO stderr: Stream to write the Lambda runtime logs to.
        :raises FunctionNotfound: When we cannot find a function with the given name
        """

        # Generate the correct configuration based on given inputs
        function = self.provider.get(function_name)

        if not function:
            raise FunctionNotFound("Unable to find a Function with name '%s'", function_name)

        LOG.debug("Found one Lambda function with name '%s'", function_name)

        if not is_installing:
            LOG.info("Invoking %s (%s)", function.handler, function.runtime)
        config = self._get_invoke_config(function)

        # Invoke the function
        self.local_runtime.invoke(config, self.cwd, event, debug_context=self.debug_context,
                                  is_installing=is_installing, stdout=stdout, stderr=stderr)

    def is_debugging(self):
        """
        Are we debugging the invoke?

        Returns
        -------
        bool
            True, if we are debugging the invoke ie. the Docker container will break into the debugger and wait for
            attach
        """
        return bool(self.debug_context)

    def _get_invoke_config(self, function):
        """
        Returns invoke configuration to pass to Lambda Runtime to invoke the given function

        :param samcli.commands.local.lib.provider.Function function: Lambda function to generate the configuration for
        :return samcli.local.lambdafn.config.FunctionConfig: Function configuration to pass to Lambda runtime
        """

        env_vars = self._make_env_vars(function)
        code_abs_path = self._get_code_path(function.codeuri)

        LOG.debug("Resolved absolute path to code is %s", code_abs_path)

        function_timeout = function.timeout

        # The Runtime container handles timeout inside the container. When debugging with short timeouts, this can
        # cause the container execution to stop. When in debug mode, we set the timeout in the container to a max 10
        # hours. This will ensure the container doesn't unexpectedly stop while debugging function code
        if self.is_debugging():
            function_timeout = self.MAX_DEBUG_TIMEOUT

        return FunctionConfig(name=function.name,
                              runtime=function.runtime,
                              handler=function.handler,
                              code_abs_path=code_abs_path,
                              memory=function.memory,
                              timeout=function_timeout,
                              env_vars=env_vars)

    def _make_env_vars(self, function):
        """
        Returns the environment variables configuration for this function

        :param samcli.commands.local.lib.provider.Function function: Lambda function to generate the configuration for
        :return samcli.local.lambdafn.env_vars.EnvironmentVariables: Environment variable configuration for this
            function
        """

        name = function.name

        variables = None
        if function.environment and isinstance(function.environment, dict) and "Variables" in function.environment:
            variables = function.environment["Variables"]
        else:
            LOG.debug("No environment variables found for function '%s'", name)

        # This could either be in standard format, or a CloudFormation parameter file format.
        #
        # Standard format is {FunctionName: {key:value}, FunctionName: {key:value}}
        # CloudFormation parameter file is {"Parameters": {key:value}}
        if "Parameters" in self.env_vars_values:
            LOG.debug("Environment variables overrides data is in CloudFormation parameter file format")
            # CloudFormation parameter file format
            overrides = self.env_vars_values["Parameters"]
        else:
            # Standard format
            LOG.debug("Environment variables overrides data is standard format")
            overrides = self.env_vars_values.get(name, None)

        shell_env = os.environ
        creds = self.get_bce_creds()

        return EnvironmentVariables(function.memory,
                                    function.timeout,
                                    function.handler,
                                    variables=variables,
                                    shell_env_values=shell_env,
                                    override_values=overrides,
                                    bce_creds=creds)

    def _get_code_path(self, codeuri):
        """
        Returns path to the function code resolved based on current working directory.

        :param string codeuri: CodeURI of the function. This should contain the path to the function code
        :return string: Absolute path to the function code
        """

        LOG.debug("Resolving code path. Cwd=%s, CodeUri=%s", self.cwd, codeuri)

        # First, let us figure out the current working directory.
        # If current working directory is not provided, then default to the directory where the CLI is running from
        if not self.cwd or self.cwd == self.PRESENT_DIR:
            self.cwd = os.getcwd()

        # Make sure cwd is an absolute path
        self.cwd = os.path.abspath(self.cwd)

        # Next, let us get absolute path of function code.
        # Codepath is always relative to current working directory
        # If the path is relative, then construct the absolute version
        if not os.path.isabs(codeuri):
            codeuri = os.path.normpath(os.path.join(self.cwd, codeuri))

        return codeuri

    def get_bce_creds(self):
        """
        Returns BCE credentials obtained from the shell environment or given profile

        :return dict: A dictionary containing credentials. This dict has the structure
             {"region": "", "key": "", "secret": "", "sessiontoken": ""}. If credentials could not be resolved,
             this returns None
        """

        result = {}
        bce_credentials = get_credentials()
        if bce_credentials.access_key_id != "":
            result["key"] = bce_credentials.access_key_id

        if bce_credentials.secret_access_key != "":
            result["secret"] = bce_credentials.secret_access_key

        # if bce_credentials.session_token != "" :
        #     result["token"] = bce_credentials.session_token

        return result
