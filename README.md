# ecs-cluster
Tools for working with AWS ECS clusters.

## Installation

`pip install git+https://github.com/silvercar/ecs-cluster`

## Usage

### updating a task image and restarting the task

This will find the running task in a service, create a new task definition with the new image,
deactivate the running task's definition, stop the running task and start a new one. This is not
intended for blue-green deployments.

`ecs-cluster --container <ecs_container_name> --service <ecs_service_name> --image <ecr_image>`

## Contributing

1. Branch off of develop, so make sure you're on develop first: `git checkout develop`
1. Create your feature branch: `git checkout -b my-new-feature`
2. Commit your changes: `git commit -am 'Add some feature'`
3. Push to the branch: `git push origin my-new-feature`
4. Submit a pull request :D
