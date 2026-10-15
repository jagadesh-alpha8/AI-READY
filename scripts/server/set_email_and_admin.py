"""Runs ON the production VM (as root), fed by scripts/set-email-and-admin.sh.

Reads four lines from stdin -- Gmail address, Gmail app password, admin email,
admin password -- so none of them appear on a command line or in a log. Then:

1. writes the email settings into /opt/ai-ready/.env (backup: .env.before-email),
2. recreates backend + celery so they pick the settings up,
3. creates or updates the admin as super_admin with that password,
4. sends a test email to the admin.
"""
import os
import re
import shutil
import subprocess
import sys
import time

APP = '/opt/ai-ready'
ENV = f'{APP}/.env'
SITE = 'https://ai.ingageedutech.com'

gmail, app_password, admin_email, admin_password = (sys.stdin.readline().strip() for _ in range(4))
app_password = app_password.replace(' ', '')
if not (gmail and app_password and admin_email and admin_password):
    sys.exit('Missing a value; nothing changed.')

values = {
    'EMAIL_HOST': 'smtp.gmail.com',
    'EMAIL_PORT': '587',
    'EMAIL_USE_TLS': 'True',
    'EMAIL_HOST_USER': gmail,
    'EMAIL_HOST_PASSWORD': app_password,
    'DEFAULT_FROM_EMAIL': f'InGage AI Readiness <{gmail}>',
    'ADMIN_EMAILS': admin_email,
    'FRONTEND_BASE_URL': SITE,
}

shutil.copy2(ENV, f'{ENV}.before-email')
lines = open(ENV, encoding='utf-8').read().splitlines()
for key, value in values.items():
    line = f"{key}='{value}'"
    for i, existing in enumerate(lines):
        if re.match(rf'^\s*{key}\s*=', existing):
            lines[i] = line
            break
    else:
        lines.append(line)
open(ENV, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
os.chmod(ENV, 0o600)
print('1/4 email settings written to .env')

subprocess.run(['docker', 'compose', 'up', '-d', '--force-recreate', '--no-deps', 'backend', 'celery'],
               cwd=APP, check=True, stdout=subprocess.DEVNULL)
for _ in range(40):
    state = subprocess.run(['docker', 'compose', 'ps', '--format', '{{.Health}}', 'backend'],
                           cwd=APP, capture_output=True, text=True).stdout.strip()
    if state == 'healthy':
        break
    time.sleep(5)
print(f'2/4 backend restarted ({state or "unknown"})')

SHELL = r'''
import os
from django.conf import settings
from django.core.mail import send_mail
from apps.accounts.models import User
email, password = os.environ['ADMIN_EMAIL'], os.environ['ADMIN_PASSWORD']
user = User.objects.filter(email__iexact=email).first()
created = user is None
if created:
    base = email.split('@')[0]
    username, n = base, 1
    while User.objects.filter(username=username).exists():
        n += 1
        username = f'{base}{n}'
    user = User(email=email, username=username, first_name=base.split('.')[0].title())
user.role = User.Role.SUPER_ADMIN
user.is_staff = user.is_superuser = user.is_active = True
user.set_password(password)
user.save()
print('3/4 admin', 'created' if created else 'updated', 'as super_admin')
send_mail('InGage AI Readiness: email is working',
          'This is a test from the AI Readiness server. Password reset emails and error alerts will come from '
          f'this address.\n\nSign in: {settings.FRONTEND_BASE_URL}/login\n',
          settings.DEFAULT_FROM_EMAIL, [email])
print('4/4 test email sent to the admin')
'''
env = dict(os.environ, ADMIN_EMAIL=admin_email, ADMIN_PASSWORD=admin_password)
subprocess.run(['docker', 'compose', 'exec', '-T', '-e', 'ADMIN_EMAIL', '-e', 'ADMIN_PASSWORD', 'backend',
                'python', 'manage.py', 'shell', '-c', SHELL], cwd=APP, env=env, check=True)
