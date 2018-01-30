from __future__ import print_function

import json
import click

from .ecs_client import ECSClient


def _get_service_arn(ecs_client, cluster, service, service_arn):
    if service is not None:
        matches = [arn for arn in ecs_client.get_services(cluster)
                   if service == arn.split('/', 1)[1]]
        if len(matches) > 0:
            service_arn = matches[0]
    if service_arn is None:
        service_arn = ecs_client.get_default_service_arn(cluster)
    return service_arn


def _get_cli_stdin(ctx, param, value):
    if not value and not click.get_text_stream('stdin').isatty():
        return click.get_text_stream('stdin').read().strip()
    else:
        return value


@click.group()
def cli():
    pass


@click.command('list-services')
@click.option("--cluster", required=True)
def list_services(cluster):
    ecs_client = ECSClient()
    print("-- services for %s --" % cluster)
    for service in ecs_client.get_services(cluster) or []:
        print("    %s" % service)
    print()


@click.command('update-image')
@click.option("--cluster", required=True)
@click.option("--service", required=False)
@click.option("--service-arn", required=False)
@click.option("--image")
def update_image(cluster, service, service_arn, image):
    ecs_client = ECSClient()
    service_arn = _get_service_arn(ecs_client, cluster, service, service_arn)

    ecs_client.redeploy_image(cluster, service_arn, image)


@click.command('update-taskdef')
@click.option("--cluster", required=True)
@click.option("--service", required=False)
@click.option("--service-arn", required=False)
@click.argument("taskdef", callback=_get_cli_stdin, required=False)
def update_taskdef(cluster, service, service_arn, taskdef):
    ecs_client = ECSClient()
    service_arn = _get_service_arn(ecs_client, cluster, service, service_arn)

    new_taskdef_arn = ecs_client.register_task_definition(json.loads(taskdef))
    old_taskdef_arn = ecs_client.get_task_definition_arn(cluster, service_arn)

    print("Replacing task def %s with task def %s for service"
          % (old_taskdef_arn, new_taskdef_arn, service_arn))

    task = ecs_client.redeploy_service_task(cluster, service_arn,
                                            old_taskdef_arn, new_taskdef_arn)

    if task is not None:
        print("Success")


cli.add_command(list_services)
cli.add_command(update_image)
cli.add_command(update_taskdef)
