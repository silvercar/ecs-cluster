# ecs-cluster
Tools for working with AWS ECS clusters.

## Installation

`pip install git+https://github.com/silvercar/ecs-cluster`

## Usage

### Updating the container image in a task definition

This will update the image in the task definition, and update the service to use this new definition.
Afterwards, the ecs-agent will take care of starting new tasks and stopping the old ones (according
to its deployment configuration/health check rules).

`ecs-cluster  update-image --cluster <cluster_name> --service <ecs_service_name> --container <ecs_container_name> --image <ecr_image>`

### SSHing into a container

`ecs-cluster ssh-service --cluster cluster-name --service service-name`

### Updating a task image and restarting the task

Same as above, except the tasks will be forcefully stopped first, and then replaced.
Note the `--restart` flag.

`ecs-cluster  update-image --cluster <cluster_name> --service <ecs_service_name> --container <ecs_container_name> --image <ecr_image> --restart`

## Contributing

1. Branch off of master, so make sure you're on master first: `git checkout master`
2. Create your feature branch: `git checkout -b my-new-feature`
3. Test your changes:
    ```bash
    $ virtualenv venv --python=python3
    $ . venv/bin/activate
    $ pip install --editable .
    $ ecs-cluster
    ```

4. Commit your changes: `git commit -am 'Add some feature'`
5. Push to the branch: `git push origin my-new-feature`
6. Submit a pull request :D
