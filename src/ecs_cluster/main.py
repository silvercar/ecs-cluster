from __future__ import print_function

import json
import sys
import sys
import click

from .ecs_client import ECSClient

def _get_service_arn(ecs_client, cluster, service):
    service_arn = None
    if service is not None:
        services = ecs_client.get_services(cluster)
        if services is None:
            click.echo(
                'Could not get ECS services. Check AWS credentials', err=True)
            sys.exit(1)
        matches = [arn for arn in services
                   if service == arn.split('/', 1)[1]]
        if len(matches) > 0:
            service_arn = matches[0]
    return service_arn

# pylint: disable=unused-argument
def _get_cli_stdin(ctx, param, value):
    if not value and not click.get_text_stream('stdin').isatty():
        return click.get_text_stream('stdin').read().strip()

    return value


@click.group()
@click.option("--timeout", required=False, type=int, default=60)
@click.pass_context
def cli(ctx, timeout):
    ctx.obj = {'timeout': timeout}


@click.command('list-services')
@click.option("--cluster", required=True)
@click.pass_context
def list_services(ctx, cluster):
    ecs_client = ECSClient(timeout=ctx.obj['timeout'])
    click.echo('-- services for %s --' % cluster)
    for service in ecs_client.get_services(cluster) or []:
        click.echo('    %s' % service)
        active_task_arn = ecs_client.get_task_definition_arn(cluster, service)
        latest_task_arn = ecs_client.get_latest_task_definition_arn(cluster, service)
        click.echo('        active: %s' % active_task_arn)
        click.echo('        latest: %s' % latest_task_arn)

    click.echo('')


@click.command('update-image', context_settings=dict(max_content_width=120))
@click.option("--cluster", required=True)
@click.option("--service", required=False)
@click.option("--service-arn", required=False)
@click.option("--hostname", required=False)
@click.option("--container", required=True)
@click.option("--image", required=True)
@click.option("--restart", is_flag=True, default=False,
              help="Force task restart after update. Defaults to false.")
@click.option("--latest", is_flag=True, default=False,
              help="Update the latest task definition, even if it's not the one currently in use")
@click.pass_context
def update_image(ctx, cluster, service, service_arn, hostname, container, image, restart, latest):
    ecs_client = ECSClient(timeout=ctx.obj['timeout'])
    service_arn = _get_service_arn(ecs_client, cluster, service)

    if service_arn is None:
        click.echo('No matching service found for cluster %s' %
                   cluster, err=True)
        sys.exit(1)

    if restart:
        service = ecs_client.redeploy_image(
            cluster, service_arn, container, image)
    else:
        service = ecs_client.update_image(
            cluster, service_arn, container, hostname, image, latest)

    if service:
        click.echo('Success')
    click.echo('')


@click.command('update-taskdef')
@click.option("--cluster", required=True)
@click.option("--service", required=False)
@click.argument("taskdef_text", callback=_get_cli_stdin, required=False)
@click.pass_context
def update_taskdef(ctx, cluster, service, service_arn, taskdef_text):
    ecs_client = ECSClient(timeout=ctx.obj['timeout'])
    service_arn = _get_service_arn(ecs_client, cluster, service)

    if service_arn is None:
        click.echo('No matching service found for cluster %s' %
                   cluster, err=True)
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

    if service:
        click.echo('Success')
    click.echo('')

@click.command('get-images')
@click.option("--cluster", required=True)
@click.option("--service", required=True)
@click.option("--container", required=False)
@click.pass_context
def get_images(ctx, cluster, service, container):
    ecs_client = ECSClient(timeout=ctx.obj['timeout'])
    task_arn = ecs_client.get_task_definition_arn(cluster, service)
    response = ecs_client.get_task_images(task_arn)
    print(json.dumps(response))

@click.command('ssh-service')
@click.option("--cluster", required=True)
@click.option("--service", required=False)
@click.option("--task-arn", required=False)
@click.option("--rails", help='enter rails console', is_flag=True, required=False, default=False)
@click.option('--user', help='ssh user, defaults to "ec2-user"', default='ec2-user')
@click.option('--keydir', required=False,
              help="Directory name in $HOME where your ssh pem files are stored", default=".ssh")
@click.option("--chamber-env", required=False)
@click.pass_context
def ssh_service(ctx, cluster, service, service_arn, task_arn, rails, user, keydir, chamber_env):
    ecs_client = ECSClient(timeout=ctx.obj['timeout'])

    service_arn = _get_service_arn(ecs_client, cluster, service)

    if service_arn is None:
        click.echo('No matching service found for cluster %s' %
                   cluster, err=True)
        sys.exit(1)

    service_cmd = 'rails console' if rails else '/bin/bash'

    if chamber_env:
        service_cmd = 'chamber exec {} -- {}'.format(chamber_env, service_cmd)

    ecs_client.ssh_to_service(cluster, service_arn,
                              task_arn, user, keydir, service_cmd)


@click.command('docker-stats')
@click.option("--cluster", required=True)
@click.option('--keydir', required=False,
              help="Directory name in $HOME where your ssh pem files are stored", default=".ssh")
@click.option('--user', help='ssh user, defaults to "ec2-user"', default='ec2-user')
@click.pass_context
def docker_stats(ctx, cluster, keydir, user):
    ecs_client = ECSClient(timeout=ctx.obj['timeout'])
    ecs_client.docker_stats(cluster, keydir, user)


cli.add_command(list_services)
cli.add_command(update_image)
cli.add_command(update_taskdef)
cli.add_command(ssh_service)
cli.add_command(docker_stats)
cli.add_command(get_images)
