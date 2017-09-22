import click

from .ecs_client import ECSClient


@click.command()
@click.option('--cluster', required=True, type=str)
@click.option('--container', required=True, type=str)
@click.option('--image', required=True, type=str)
def cli(cluster, container, image):
    ecs_client = ECSClient()
    ecs_client.redeploy_image(cluster, container, image)
