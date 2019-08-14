import os
import boto3
from botocore.exceptions import ClientError
import polling
import requests
import paramiko


def _print_error(msg):
    print('Error: ' + msg)

class ECSClient:
    """
    Abstraction of the boto ecs client
    """

    def __init__(self, timeout=60):
        self.ecs_client = boto3.client('ecs')
        self.ec2_client = boto3.client('ec2')
        self.timeout = timeout

    def redeploy_service_task(self, cluster_name, service_arn,
                              old_taskdef_arn, new_taskdef_arn):
        """ Redploys a service. This will stop the service's running task and
            deregister it, then restart the service with the new task
            definition.
        """
        # Deregister the old task definition
        self.deregister_task_definition(old_taskdef_arn)

        # Stops tasks similar to the old task definition
        self.stop_tasks_similar_to_task_definition(
            cluster_name, old_taskdef_arn)

        service = self.update_service(cluster_name, service_arn, new_taskdef_arn)
        if not service:
            _print_error("Unable to update the service %s with task %s" %
                         (service_arn, new_taskdef_arn))
            return False

        def _echo_poll_step(step):
            print('waiting for service to restart...')
            return step

        try:
            polling.poll(
                lambda: self.redeploy_poll(cluster_name, service, service_arn),
                step=5,
                step_function=_echo_poll_step,
                timeout=self.timeout
            )

        except polling.PollingException:
            _print_error("Timeout or max tries exceeded")
            return False

        return True

    def redeploy_poll(self, cluster_name, service, service_arn):
        running_count = self.get_service(cluster_name, service_arn)['runningCount']
        return running_count == service['desiredCount']

    def redeploy_image(self, cluster_name, service_arn, container_name, image_name):
        """ Redeploys a service while updating the image in its task
            definition.

            This will find the service's task definition and create a new
            revision with an updated image name for the specified container.
            It will then stop the running tasks and restart them with the new
            definition.
        """
        old_taskdef_arn = self.get_task_definition_arn(cluster_name, service_arn)
        if old_taskdef_arn is None:
            _print_error(
                "No task definition found for service " + service_arn)
            return False

        new_taskdef_arn = self.clone_task(old_taskdef_arn,
                                          container_name,
                                          image_name)
        if new_taskdef_arn is None:
            _print_error(
                "Unable to clone the task definition " + old_taskdef_arn)
            return False

        self.ecs_client.tag_resource(resourceArn=new_taskdef_arn, tags=[{'key': 'Managed', 'value': 'ecs-cluster'}])

        service = self.redeploy_service_task(cluster_name,
                                             service_arn,
                                             old_taskdef_arn,
                                             new_taskdef_arn)
        return service

    def update_image(self, cluster_name, service_arn, container_name,
                     hostname, image_name, entrypoint=None, command=None):
        """ Update the image in a task definition

            Same as redeploy_image, except the tasks won't be stopped. Instead,
            we'll let the ecs-agent do its thing and replace the tasks following
            whatever deployment strategy is configured.
        """
        latest_task_definition_arn = self.get_latest_task_definition_arn(cluster_name, service_arn, search_tag='ecs-cluster')

        if latest_task_definition_arn is None:
            _print_error(
                "No task definition found for service " + service_arn)
            return False

        new_taskdef_arn = self.clone_task(latest_task_definition_arn,
                                          container_name,
                                          image_name,
                                          hostname,
                                          entrypoint,
                                          command)
        if new_taskdef_arn is None:
            _print_error(
                "Unable to clone the task definition " + latest_task_definition_arn)
            return False
        
        self.ecs_client.tag_resource(resourceArn=new_taskdef_arn, tags=[{'key': 'Managed', 'value', 'ecs-cluster'}])

        self.deregister_task_definition(latest_task_definition_arn)

        service = self.update_service(cluster_name, service_arn, new_taskdef_arn)
        if not service:
            _print_error("Unable to update the service %s with task %s"
                         % (service_arn, new_taskdef_arn))
            return False

        return True

    def get_services(self, cluster_name):
        """ Returns the ARN of all services found for the cluster
        """
        try:
            response = self.ecs_client.list_services(cluster=cluster_name)
        except ClientError:
            _print_error(
                "Error getting list of services for %s" % cluster_name)
            return None
        return response['serviceArns']

    def get_service(self, cluster_name, service_arn):
        """ Returns the service object matching the service ARN
        """
        response = self.ecs_client.describe_services(cluster=cluster_name,
                                                     services=[service_arn])
        if response is None or not response['services']:
            return None
        for service in response['services']:
            if service['serviceArn'] == service_arn:
                return service

        _print_error("No service for cluster %s matches %s" %
                     (cluster_name, service_arn))
        return None

    def get_task_family(self, taskdef_arn):
        """ Returns the family of a task definition
        """
        response = self.ecs_client.describe_task_definition(
            taskDefinition=taskdef_arn)
        if response is None or 'taskDefinition' not in response:
            return ''
        return response['taskDefinition']['family']

    def get_task_arn(self, cluster_name, service_name):
        response = self.ecs_client.list_tasks(
            cluster=cluster_name, serviceName=service_name)
        if response is None or 'taskArns' not in response:
            return ''
        return response['taskArns'][0]

    def get_task_definition_arn(self, cluster_name, service_arn):
        """ Returns the ARN of the task definition which matches the
            service name
        """
        service = self.get_service(cluster_name, service_arn)
        if service is not None:
            return service['taskDefinition']
        return None

    def get_latest_task_definition_arn(self, cluster_name, service_name, search_tag=''):

        active_arn = self.get_task_definition_arn(cluster_name, service_name)
        family = self.get_task_family(active_arn)

        # for task in tasks:
        response = self.ecs_client.list_task_definitions(
            familyPrefix=family,
            status='ACTIVE',
            sort='DESC'
        )
        if not search_tag: 
            latest_arn = response['taskDefinitionArns'][0]
            return latest_arn
        else:
            for task_definition_arn in response['taskDefinitionArns']:
                tags = self.ecs_client.list_tags_for_resource(resourceArn=task_definition_arn).get('tags')
                for tag in tags:
                    if tag['key'] == 'Managed' and tag['value'] == 'ecs-cluster':
                        return task_definition_arn
            print("Unable to find a task definition that is tagged 'Managed=%s', returning 'None'" % search_tag)
            return None

    def register_task_definition(self, register_kwargs):
        response = self.ecs_client.register_task_definition(**register_kwargs)
        new_task_definition_arn = response['taskDefinition']['taskDefinitionArn']

        return new_task_definition_arn

    def get_task_images(self, task_definition_arn):
        response = self.ecs_client.describe_task_definition(
            taskDefinition=task_definition_arn)
        return [{'container': x['name'], 'image': x['image']} for x in
                response['taskDefinition']['containerDefinitions']]

    def clone_task(self, task_definition_arn, container_name, image_name,
                   hostname=None, entrypoint=None, command=None):
        """ Clones a task and sets its image attribute. Returns the new
            task definition arn if successful, otherwise None
        """
        response = self.ecs_client.describe_task_definition(
            taskDefinition=task_definition_arn)

        if response is None or 'taskDefinition' not in response:
            return None

        task_def = response['taskDefinition']
        containers = task_def['containerDefinitions']

        # Update the image in the container
        for container in containers:
            if container['name'] == container_name:
                container['image'] = image_name
                if hostname is not None:
                    container['hostname'] = hostname
                if entrypoint is not None:
                    container['entryPoint'] = entrypoint.split()
                if command is not None:
                    container['command'] = command.split()
        task_def['containerDefinitions'] = containers

        # Remove fields not required for new task def
        task_def.pop('revision')
        task_def.pop('status')
        task_def.pop('taskDefinitionArn')
        task_def.pop('compatibilities')
        task_def.pop('requiresAttributes')

        return self.register_task_definition(task_def)

    def update_service(self, cluster_name, service_name, task_definition_arn):
        """ Updates the service with a different task definition. Returns
            the service response if successful, otherwise None
        """
        response = self.ecs_client.update_service(cluster=cluster_name,
                                                  service=service_name,
                                                  taskDefinition=task_definition_arn)
        if response is None or 'service' not in response \
                or response['service']['status'] != 'ACTIVE':
            return False

        return True

    def deregister_task_definition(self, task_definition_arn):
        """ Deregisters the specified task definition. Returns the task
            definition if successful, None otherwise
        """
        response = self.ecs_client.deregister_task_definition(
            taskDefinition=task_definition_arn)
        if response is None or 'taskDefinition' not in response \
                or response['taskDefinition'].get('status', None) != 'INACTIVE':
            return None

        return response['taskDefinition']

    def stop_tasks_similar_to_task_definition(self, cluster_name, task_definition):
        """ Stops all running tasks similar a task definition. Similarity
            is measured by the task definition family name. If two task definition
            arns only vary by the revision, they will have the same family
            Returns the stopped tasks if successful, None otherwise
        """
        response = self.ecs_client.describe_task_definition(
            taskDefinition=task_definition)

        if response is None or 'taskDefinition' not in response:
            return None

        family = response['taskDefinition']['family']

        response = self.ecs_client.list_tasks(cluster=cluster_name,
                                              family=family,
                                              desiredStatus='RUNNING')
        if response is None or 'taskArns' not in response:
            _print_error("No running tasks found")
            return None

        stopped = []

        for task_arn in response['taskArns']:
            response = self.ecs_client.stop_task(
                cluster=cluster_name, task=task_arn)

            if response is None or 'task' not in response:
                _print_error("Could not stop task %s" % task_arn)

            stopped.append(response['task'])

        return stopped

    def start_task(self, cluster_name, task_definition):
        """ Starts a new task for the task_definition. Returns the started task
            if successful, None otherwise.
        """
        response = self.ecs_client.run_task(
            cluster=cluster_name, taskDefinition=task_definition)
        if response is None or 'tasks' not in response \
                or not response['tasks']:
            return None
        return response['tasks'][0]

    # pylint: disable=too-many-locals
    def docker_stats(self, cluster_name, ssh_keydir, user):
        arns = [x for x in self.ecs_client.list_container_instances(
            cluster=cluster_name)["containerInstanceArns"]]
        host_ids = [x["ec2InstanceId"] for x in self.ecs_client.describe_container_instances(
            cluster=cluster_name, containerInstances=arns)["containerInstances"]]
        hosts = [self._get_ec2_details(x) for x in host_ids]

        for host in hosts:
            if 'PublicIpAddress' in host:
                ip_address = host['PublicIpAddress']
            else:
                ip_address = host['PrivateIpAddress']

            key_name = host['KeyName']
            pem_file = self._get_ssh_key(ssh_keydir, key_name)
            command = "docker stats --no-stream --no-trunc"
            ssh_client = paramiko.SSHClient()
            ssh_client.load_system_host_keys()
            ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy)
            ssh_client.connect(hostname=ip_address,
                               username=user,
                               key_filename=pem_file)

            print('Host ' + ip_address)

            # pylint: disable=unused-variable
            stdin, stdout, stderr = ssh_client.exec_command(command)
            for line in stdout:
                print(line.strip('\n'))
            ssh_client.close()

    # pylint: disable=too-many-locals
    def ssh_to_service(self, cluster_name, service_arn, task_arn,
                       ssh_user, ssh_key_dir, service_cmd):
        service = self.get_service(cluster_name, service_arn)
        if service is None:
            _print_error(
                "Could not find service %s in cluster %s" % (service_arn, cluster_name))
            return None

        if not task_arn:
            task_arn = self.get_task_arn(cluster_name, service_arn)

        ec2_arn = self._get_ec2_arn(cluster_name, service_arn, task_arn)
        ec2_details = self._get_ec2_details(ec2_arn)
        if 'PublicIpAddress' in ec2_details:
            ip_address = ec2_details['PublicIpAddress']
        else:
            ip_address = ec2_details['PrivateIpAddress']

        key_name = ec2_details['KeyName']
        pem_file = self._get_ssh_key(ssh_key_dir, key_name)

        container_id = self._find_container_id(ip_address, task_arn)
        docker_cmd = 'docker exec ' \
                     '-e COLUMNS="`tput cols`" ' \
                     '-e LINES="`tput lines`" -it {} {}'.format(container_id, service_cmd)
        system_cmd = 'ssh -t -o StrictHostKeyChecking=no ' \
                     '-o TCPKeepAlive=yes ' \
                     '-o ServerAliveInterval=50 -i {} {}@{} {}' \
            .format(pem_file, ssh_user, ip_address, docker_cmd)

        print("==========================================================")
        print(' Container Id {}'.format(container_id))
        print(' Service Command {}'.format(service_cmd))
        print(' SSH User {}'.format(ssh_user))
        print(' IP Address {}'.format(ip_address))
        print(' Key {}'.format(pem_file))
        print(' Docker Command {}'.format(docker_cmd))
        print(' Full Command {}'.format(system_cmd))
        print("==========================================================")

        os.system(system_cmd)

        return None

    def _get_ec2_arn(self, cluster_name, service_arn, task_arn):
        if service_arn:
            instances = self._get_service_container_instances(
                cluster_name, service_arn, task_arn)
        else:
            instances = self._get_container_instances(cluster_name)
        with_tasks = [i for i in instances if i['runningTasksCount'] > 0]
        return with_tasks[0]['ec2InstanceId']

    def _get_service_container_instances(self, cluster_name, service_arn, task_arn):
        """
        Enum all instances in the cluster running containers related to the target service
        """
        if not task_arn:
            task_arn = self.get_task_arn(cluster_name, service_arn)

        tasks = self.ecs_client.describe_tasks(
            cluster=cluster_name, tasks=[task_arn])['tasks']
        containers = [x['containerInstanceArn'] for x in tasks]
        response = self.ecs_client.describe_container_instances(
            cluster=cluster_name,
            containerInstances=containers
        )
        return response['containerInstances']

    def _get_container_instances(self, cluster_name):
        arns = self.ecs_client.list_container_instances(
            cluster=cluster_name)['containerInstanceArns']
        response = self.ecs_client.describe_container_instances(
            cluster=cluster_name,
            containerInstances=arns
        )

        return response['containerInstances']

    @staticmethod
    def _find_container_id(ip_address, task_arn):
        """
        Query the ECS agent to obtain the local docker container id
        which is needed during the docker exec phase
        """
        url = 'http://%s:51678/v1/tasks' % ip_address
        response = requests.get(url=url)
        data = response.json()
        tasks = [task for task in data['Tasks'] if task['Arn'] == task_arn]
        if not tasks:
            _print_error("No container found for task %s" % task_arn)
            return None
        # There should only be 1 task matching the task_arn
        # This also assumes there is 1 container per task, maybe that's not always true?
        return [container['DockerId'] for container in tasks[0]['Containers']][0]

    def _get_ec2_details(self, ec2_arn):
        ids = [ec2_arn]
        response = self.ec2_client.describe_instances(InstanceIds=ids)
        details = response['Reservations'][0]['Instances'][0]
        return details

    @staticmethod
    def _get_ssh_key(key_dir, key_name):

        home = os.environ['HOME']
        path = os.path.join(home, key_dir, '%s.pem' % key_name)
        if not os.path.exists(path):
            path = os.path.join(home, key_dir, 'id_rsa')
            if not os.path.exists(path):
                raise FileNotFoundError('Could not find valid ssh key')

        return path
