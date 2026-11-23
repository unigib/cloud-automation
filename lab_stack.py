import base64
import ipaddress
from pathlib import Path

from aws_cdk import (
    CfnOutput,
    RemovalPolicy,
    Stack,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct


class StudentLabStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs: object) -> None:
        super().__init__(scope, construct_id, **kwargs)

        allowed_ip = self.node.try_get_context("allowed_ip")
        if not isinstance(allowed_ip, str):
            raise ValueError("Provide your public IPv4 address as -c allowed_ip=x.x.x.x/32")
        try:
            network = ipaddress.ip_network(allowed_ip, strict=True)
        except ValueError as exc:
            raise ValueError("allowed_ip must be a public IPv4 address with a /32 mask") from exc
        if network.version != 4 or network.prefixlen != 32 or not network.network_address.is_global:
            raise ValueError("allowed_ip must be a public IPv4 address with a /32 mask")

        vpc = ec2.Vpc(
            self,
            "LabVpc",
            max_azs=1,
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(name="Public", subnet_type=ec2.SubnetType.PUBLIC)
            ],
        )
        security_group = ec2.SecurityGroup(self, "WebSecurityGroup", vpc=vpc)
        security_group.add_ingress_rule(ec2.Peer.ipv4(str(network)), ec2.Port.tcp(8080), "Student web access")

        secret = secretsmanager.Secret(
            self,
            "DatabaseSecret",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"username":"labuser"}',
                generate_string_key="password",
                exclude_punctuation=True,
                password_length=32,
            ),
            removal_policy=RemovalPolicy.DESTROY,
        )

        instance = ec2.Instance(
            self,
            "WebServer",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            instance_type=ec2.InstanceType("t3.micro"),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            security_group=security_group,
            require_imdsv2=True,
            user_data_causes_replacement=True,
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(8, encrypted=True, delete_on_termination=True),
                )
            ],
        )
        instance.role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore")
        )
        secret.grant_read(instance.role)

        files_dir = Path(__file__).parent / "webapp"
        files = ("app.py", "init_db.py", "requirements.txt", "student-lab.service")
        commands = [
            "set -euxo pipefail",
            "dnf install -y mariadb105-server python3-pip",
            "printf '[mysqld]\\nbind-address=127.0.0.1\\nskip-name-resolve\\n' > /etc/my.cnf.d/student-lab.cnf",
            "systemctl enable --now mariadb",
            "useradd --system --no-create-home --shell /sbin/nologin labapp",
            "mkdir -p /opt/student-lab",
        ]
        for filename in files:
            encoded = base64.b64encode((files_dir / filename).read_bytes()).decode("ascii")
            commands.append(f"echo '{encoded}' | base64 -d > /opt/student-lab/{filename}")
        commands.extend([
            "python3 -m venv /opt/student-lab/venv",
            "/opt/student-lab/venv/bin/pip install -r /opt/student-lab/requirements.txt",
            f"printf 'AWS_REGION=%s\\nSECRET_ARN=%s\\n' '{self.region}' '{secret.secret_arn}' > /opt/student-lab/environment",
            "cp /opt/student-lab/student-lab.service /etc/systemd/system/student-lab.service",
            "systemctl daemon-reload",
            "systemctl enable --now student-lab",
        ])
        instance.add_user_data(*commands)

        CfnOutput(self, "WebUrl", value=f"http://{instance.instance_public_ip}:8080")
        CfnOutput(self, "InstanceId", value=instance.instance_id)
        CfnOutput(self, "SecretArn", value=secret.secret_arn)
