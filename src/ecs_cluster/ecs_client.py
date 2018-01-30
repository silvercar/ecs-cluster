import boto3
import click


class ECSClient(object):
    def __init__(self):
        self.client = boto3.client('ecs')

    def _print_error(self, msg):
        print('Error: ' + msg)

    def redeploy_service_task(self, cluster_name, service_arn,
                              old_taskdef_arn, new_taskdef_arn):
        service = self.update_service(cluster_name, service_arn, new_taskdef_arn)
        if service is None:
            self._print_error("Unable to update the service %s with task %s"
                              % (service_arn, new_taskdef_arn))

        # Dereister the old task definition
        self.deregister_task_definition(old_taskdef_arn)

        # Stops tasks similar to the old task definition
        self.stop_tasks_similar_to_task_definition(cluster_name, old_taskdef_arn)

        # Start the new task
        task = self.start_task(cluster_name, new_taskdef_arn)
        if task is None:
            self._print_error("Unable to start the task %s in cluster %s"
                              % (new_taskdef_arn, cluster_name))
        return task

    def redeploy_image(self, cluster_name, service_arn, image_name):
        if service_arn is None:
            self._print_error("No service found for cluster " + cluster_name)
            return None

        old_taskdef_arn = self.get_task_definition_arn(cluster_name, service_arn)
        if old_taskdef_arn is None:
            self._print_error("No task definition found for service " + service_arn)
            return None

        new_taskdef_arn = self.clone_task(cluster_name,
                                          old_taskdef_arn,
                                          image_name)
        if new_taskdef_arn is None:
            self._print_error("Unable to clone the task definition " + old_taskdef_arn)
            return None

        task = self.redeploy_service_task(cluster_name, service_arn,
                                          old_taskdef_arn, new_taskdef_arn)
        if task is not None:
            print("Success")

    def get_services(self, cluster_name):
        """ Returns the ARN of all services found for the cluster
        """
        try:
            response = self.client.list_services(cluster=cluster_name)
        except Exception as ex:
            return None
        return response['serviceArns']

    def get_default_service_arn(self, cluster_name):
        """ Returns the ARN of the first service found for the cluster
        """
        try:
            response = self.client.list_services(cluster=cluster_name)
        except Exception as ex:
            return None
        if response is None or len(response['serviceArns']) == 0:
            return None
        return response['serviceArns'][0]

    def get_task_definition_arn(self, cluster_name, service_name):
        """ Returns the ARN of the task definition which matches the
            service name
        """
        response = self.client.describe_services(cluster=cluster_name,
                                                 services=[service_name])
        if response is None or len(response['services']) == 0:
            return None
        for service in response['services']:
            if service['serviceArn'] == service_name:
                return service['taskDefinition']
        return None

    def register_task_definition(self, register_kwargs):
        response = self.client.register_task_definition(**register_kwargs)
        new_task_definition_arn = response['taskDefinition']['taskDefinitionArn']

        return new_task_definition_arn

    def clone_task(self, task_definition_arn, container_name,
                   image_name):
        """ Clones a task and sets its image attribute. Returns the new
            task definition arn if successful, otherwise None
        """
        response = self.client.describe_task_definition(taskDefinition=task_definition_arn)
        if response is None or 'taskDefinition' not in response:
            return None
        containers = response['taskDefinition']['containerDefinitions']
        family = response['taskDefinition']['family']

        # Update the image in the container
        for container in containers:
            if container['name'] == container_name:
                container['image'] = image_name

        register_kwargs = {"family":family, "containerDefinitions": containers}
        if 'taskRoleArn' in  response['taskDefinition']:
            register_kwargs['taskRoleArn'] = response['taskDefinition']['taskRoleArn']
        if 'networkMode' in  response['taskDefinition']:
            register_kwargs['networkMode'] = response['taskDefinition']['networkMode']

        return self.register_task_definition(register_kwargs)

    def update_service(self, cluster_name, service_name, task_definition_arn):
        """ Updates the service with a different task deinifition. Returns
            the service response if successful, otherwise None
        """
        response = self.client.update_service(cluster=cluster_name,
                                              service=service_name,
                                              taskDefinition=task_definition_arn)
        if response is None or 'service' not in response \
                or response['service']['status'] != 'ACTIVE':
            return None

        return response['service']

    def deregister_task_definition(self, task_definition_arn):
        """ Deregisters the specified task definition. Returns the task
            definition if successful, None otherwise
        """
        response = self.client.deregister_task_definition(taskDefinition=task_definition_arn)
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
        response = self.client.describe_task_definition(taskDefinition=task_definition)

        if response is None or 'taskDefinition' not in response:
            return None

        family = response['taskDefinition']['family']

        response = self.client.list_tasks(cluster=cluster_name,
                                          family=family,
                                          desiredStatus='RUNNING')
        if response is None or 'taskArns' not in response:
            self._print_error("No running tasks found")
            return None

        stopped = []

        for task_arn in response['taskArns']:
            response = self.client.stop_task(cluster=cluster_name, task=task_arn)

            if response is None or 'task' not in response:
                self._print_error("Could not stop task %s" % task_arn)

            stopped.append(response['task'])

        return stopped

    def start_task(self, cluster_name, task_definition):
        """ Starts a new task for the task_definition. Returns the started task
            if successful, None otherwise.
        """
        response = self.client.run_task(cluster=cluster_name, taskDefinition=task_definition)

        if response is None or 'tasks' not in response \
                or len(response['tasks']) == 0:
            return None

        return response['tasks'][0]
