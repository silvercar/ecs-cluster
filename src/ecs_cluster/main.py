from __future__ import print_function

import json
import sys

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
@click.option("--timeout", required=False, type=int, default=60)
@click.pass_context
def cli(ctx, timeout):
    ctx.obj = {'timeout':timeout}


@click.command('list-services')
@click.option("--cluster", required=True)
def list_services(cluster):
    ecs_client = ECSClient()
    click.echo('-- services for %s --' % cluster)
    for service in ecs_client.get_services(cluster) or []:
        click.echo('    %s' % service)
    click.echo('')


@click.command('update-image')
@click.option("--cluster", required=True)
@click.option("--service", required=False)
@click.option("--service-arn", required=False)
@click.option("--container", required=True)
@click.option("--image")
@click.pass_context
def update_image(ctx, cluster, service, service_arn, container, image):
    ecs_client = ECSClient(timeout=ctx.obj['timeout'])
    service_arn = _get_service_arn(ecs_client, cluster, service, service_arn)

    if service_arn is None:
        click.echo('No matching service found for cluster %s' % cluster, err=True)
        list_services(cluster)
        sys.exit(1)

    service = ecs_client.redeploy_image(cluster, service_arn, container, image)
    if service is not None:
        click.echo('Success')
    click.echo('')


@click.command('update-taskdef')
@click.option("--cluster", required=True)
@click.option("--service", required=False)
@click.option("--service-arn", required=False)
@click.argument("taskdef_text", callback=_get_cli_stdin, required=False)
@click.pass_context
def update_taskdef(ctx, cluster, service, service_arn, taskdef_text):
    ecs_client = ECSClient(timeout=ctx.obj['timeout'])
    service_arn = _get_service_arn(ecs_client, cluster, service, service_arn)

    if service_arn is None:
        click.echo('No matching service found for cluster %s' % cluster, err=True)
        list_services(cluster)
        sys.exit(1)

    old_taskdef_arn = ecs_client.get_task_definition_arn(cluster, service_arn)
    taskdef = json.loads(taskdef_text)

    # make sure the family is the same as the old task
    taskdef['family'] = ecs_client.get_task_family(old_taskdef_arn)

    new_taskdef_arn = ecs_client.register_task_definition(taskdef)

    service = ecs_client.redeploy_service_task(cluster,
                                               service_arn,
                                               old_taskdef_arn,
                                               new_taskdef_arn)

    if service is not None:
        click.echo('Success')
    click.echo('')

cli.add_command(list_services)
cli.add_command(update_image)
cli.add_command(update_taskdef)
