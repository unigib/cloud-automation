# Student lab: Infrastructure as Code with Python and AWS

Build a small guestbook using **Python AWS CDK**, an EC2 instance, a Python web
server, MariaDB and AWS Secrets Manager. CDK turns Python definitions into an
AWS CloudFormation template; CloudFormation creates and deletes the resources.

## Learning goals

- Inspect the relationship between CDK code, a synthesized template and AWS resources.
- Use an EC2 instance role to retrieve a generated database password without
  putting it in source code or EC2 user data.
- Create, change and destroy an environment using infrastructure as code.

## Architecture and safety

The stack creates a VPC with one public subnet and no NAT gateway, an EC2
instance with an encrypted root volume, a security group, an instance role and
a Secrets Manager secret. On first boot, EC2 user data installs MariaDB and the
Python dependencies, then starts the application with systemd. The database is
local to the instance; only port 8080 is opened, and only to your specified
public IPv4 address. AWS Systems Manager Session Manager provides shell access
without opening SSH.

This is a **temporary teaching environment, not a production design**. HTTP is
unencrypted, the guestbook has no authentication and the database is on the
same machine as the app. Anyone sharing the allowed public IP can access the
guestbook. Do not enter sensitive data. The instance and its
database are not backed up; replacing or deleting it destroys its data. A change
to the application or startup script replaces the instance on deployment.

**AWS charges may apply**, including for EC2, EBS, public IPv4, Secrets Manager,
API requests and CDK bootstrap resources, even when the lab is not in use.
Check your account's pricing, budget and permissions before deploying. Destroy
the lab immediately after use.

## Prerequisites

- An AWS account where you are authorized to create VPC, EC2, IAM, Secrets
  Manager and CloudFormation resources, and sufficient account quotas.
- AWS CLI configured with credentials and a default region (`aws configure` or
  your organization's SSO process). Use a region supporting Amazon Linux 2023
  and `t3.micro`.
- Python 3.9 or newer, Node.js and npm. The CDK CLI is run with `npx` below.
- A public IPv4 address that belongs to your current internet connection.
  Corporate proxies, VPNs and changing addresses can affect which address AWS
  sees. Use a `/32` mask; the stack rejects broader or non-public ranges.

## 1. Prepare

Commands below use PowerShell on Windows; use the corresponding virtual
environment activation command on other platforms. Run from this directory.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
aws sts get-caller-identity
aws configure get region
```

Set the public IPv4 address that will access the application (replace the
example). This is an address, not your AWS access key or database password.

```powershell
$AllowedIp = "YOUR.PUBLIC.IP.ADDRESS/32"
```

If needed, your network administrator can provide your public IPv4 address.
Alternatively, `Invoke-RestMethod https://checkip.amazonaws.com` asks AWS's
public IP service for the address seen by that request.
If it changes, update `$AllowedIp` and redeploy. If a browser uses a different
VPN or proxy, use the address seen from that browser's connection.

## 2. Inspect and deploy

Bootstrap CDK **once per account and region** if it has not already been
bootstrapped. This creates a shared CloudFormation stack and supporting
resources; coordinate with your instructor before doing so.

```powershell
npx --yes aws-cdk bootstrap
npx --yes aws-cdk synth -c allowed_ip=$AllowedIp
npx --yes aws-cdk diff -c allowed_ip=$AllowedIp
npx --yes aws-cdk deploy -c allowed_ip=$AllowedIp
```

Read the synthesized CloudFormation template and the deployment diff. Confirm
the changes when prompted. Copy the `WebUrl` and `InstanceId` outputs.
CloudFormation finishes creating the instance before its first-boot software
installation necessarily finishes; allow several minutes, then open `WebUrl`.
Add a message and refresh the page to see it read back from MariaDB.

If the page is unavailable, check your public IP, the deployment region and
the instance's Systems Manager status. In the AWS console, open Systems
Manager > Session Manager and start a session using the output `InstanceId`.
The SSM agent needs time and outbound internet access to register. Inspect:

```bash
sudo tail -n 100 /var/log/cloud-init-output.log
sudo systemctl status mariadb student-lab --no-pager
sudo journalctl -u student-lab -n 100 --no-pager
```

Fix the underlying error before restarting with `sudo systemctl restart
student-lab`. Initialization errors are reported in the service logs; do not
paste credentials into logs or share them.

## 3. Explore

1. In [lab_stack.py](lab_stack.py), find the security group, instance, secret and the
   `secret.grant_read(instance.role)` permission. Find their corresponding
   CloudFormation resources in the synth output and in the AWS console.
2. Read [init_db.py](webapp/init_db.py): the instance role obtains the secret, then the
   local MariaDB root account creates the database and a restricted app user.
   Read [app.py](webapp/app.py) to see the app retrieve that secret and use
   parameterized queries. Never print or submit the password.
3. Change the guestbook heading in [app.py](webapp/app.py). Run `diff` and `deploy`
   again with the same context. Explain why the EC2 instance is replaced and
   confirm that the previous messages are gone.
4. Try an invalid or overly broad `allowed_ip` with `synth` and observe that
   the stack rejects it. Restore your `/32` for deployment and cleanup.

The password is generated by Secrets Manager; it is not an AWS login credential.
The instance role supplies temporary AWS credentials automatically. This lab
does not configure secret rotation: changing the stored password independently
of MariaDB interrupts the app until the service is restarted.

## 4. Clean up

```powershell
npx --yes aws-cdk destroy -c allowed_ip=$AllowedIp
```

Confirm deletion and verify that the `StudentWebLab` stack and its resources
are gone in CloudFormation. The EC2 volume and its messages are permanently
deleted. The stack requests deletion of its secret; check Secrets Manager for
any remaining scheduled deletion. The shared `CDKToolkit` bootstrap stack is
**not** removed by this command and may be used by other projects. Do not
delete it without coordinating with its owners. Check the billing console for
remaining billable resources.

## Local checks

Install the web application's dependencies as well as `requirements.txt`, then
run the tests; they mock the database and AWS API and do not deploy resources:

```powershell
python -m pip install -r webapp\requirements.txt
python -m unittest discover -s tests -v
```
