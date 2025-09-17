from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, SubmitField, SelectMultipleField, TextAreaField, TimeField
from wtforms import PasswordField, BooleanField, IntegerField
from wtforms.validators import DataRequired, Email, URL, Optional, EqualTo
import pytz

class ChangePasswordForm(FlaskForm):
    password = PasswordField('New Password', validators=[DataRequired()])
    confirm_password = PasswordField('Confirm New Password', validators=[DataRequired(), EqualTo('password', message='Passwords must match')])
    submit = SubmitField('Change Password')

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember Me')
    submit = SubmitField('Login')

class UserForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired(), EqualTo('confirm', message='Passwords must match')])
    confirm = PasswordField('Repeat Password')
    role = SelectField('Role', choices=[('view', 'View Only'), ('edit', 'Edit')], validators=[DataRequired()])
    submit_user = SubmitField('Create User')

class GeneralSettingsForm(FlaskForm):
    timezone = SelectField('Timezone', choices=[(tz, tz) for tz in pytz.all_timezones], validators=[DataRequired()])
    login_required = BooleanField('Login Required')
    
    # Custom text settings
    site_name = StringField('Site Name', validators=[Optional()], description='Text shown in navigation header (default: Python Monitor)')
    footer_text = StringField('Footer Text', validators=[Optional()], description='Text shown in footer (default: Python Monitor - Open Source Uptime Monitoring)')
    site_icon = StringField('Site Icon', validators=[Optional()], description='FontAwesome icon class for navigation header (default: fas fa-heartbeat)')
    favicon_url = StringField('Favicon URL', validators=[Optional()], description='URL to custom favicon image (PNG, ICO, or SVG)')
    
    submit_general = SubmitField('Save Settings')

class NotificationChannelForm(FlaskForm):
    name = StringField('Channel Name', validators=[DataRequired()])
    channel_type = SelectField('Channel Type', choices=[
        ('email', 'Email'),
        ('webhook', 'Webhook'),
        ('slack', 'Slack')
    ], validators=[DataRequired()])
    monitors = SelectMultipleField('Associated Monitors', coerce=int, validators=[Optional()])

    # Email fields
    email_to = StringField('Recipient Email', validators=[Optional(), Email()])
    smtp_server = StringField('SMTP Server', validators=[Optional()])
    smtp_port = IntegerField('SMTP Port', validators=[Optional()])
    smtp_username = StringField('SMTP Username', validators=[Optional()])
    smtp_password = PasswordField('SMTP Password', validators=[Optional()])
    use_tls = BooleanField('Use TLS', default=False)
    use_ssl = BooleanField('Use SSL', default=False)

    # Webhook fields
    webhook_url = StringField('Webhook URL', validators=[Optional(), URL()])

    # Slack fields
    slack_webhook_url = StringField('Slack Webhook URL', validators=[Optional(), URL()])

    is_active = BooleanField('Active', default=True)
    submit = SubmitField('Save Channel')

    def __init__(self, *args, **kwargs):
        super(NotificationChannelForm, self).__init__(*args, **kwargs)
        self.instance = kwargs.get('obj')

class CommandForm(FlaskForm):
    name = StringField('Command Name', validators=[DataRequired()])
    script = TextAreaField('Script', validators=[DataRequired()], render_kw={"rows": 10})
    shell_type = SelectField('Shell Type', choices=[
        ('powershell', 'PowerShell (Windows)'),
        ('bash', 'Bash (Linux)')
    ], validators=[DataRequired()])
    trigger = SelectField('Trigger', choices=[
        ('manual', 'Manual'),
        ('schedule', 'Schedule'),
        ('on_down', 'On Monitor Down')
    ], validators=[DataRequired()])
    schedule = StringField('Schedule (Cron format)', validators=[Optional()], description="e.g., '*/5 * * * *' for every 5 minutes.")
    submit = SubmitField('Save Command')

class BackupForm(FlaskForm):
    name = StringField('Backup Name', validators=[DataRequired()], default='Auto Backup')
    backup_path = StringField('Backup Directory Path', validators=[DataRequired()], 
                              description='Full path to the directory where backups will be saved')
    frequency = SelectField('Backup Frequency', choices=[
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly')
    ], validators=[DataRequired()], default='weekly')
    time = StringField('Backup Time (HH:MM)', validators=[DataRequired()], 
                       default='02:00', description='Time of day to perform backup (24-hour format)')
    day_of_week = SelectField('Day of Week (for weekly)', choices=[
        ('0', 'Sunday'),
        ('1', 'Monday'),
        ('2', 'Tuesday'),
        ('3', 'Wednesday'),
        ('4', 'Thursday'),
        ('5', 'Friday'),
        ('6', 'Saturday')
    ], default='0', description='Only used for weekly backups')
    day_of_month = IntegerField('Day of Month (for monthly)', default=1, 
                                description='Day of month (1-28) for monthly backups')
    retention_days = IntegerField('Retention Period (days)', default=30, validators=[DataRequired()],
                                  description='How many days to keep old backup files')
    is_active = BooleanField('Enable Auto Backup', default=True)
    include_logs = BooleanField('Include Log Files', default=False, 
                                description='Include agent logs and system logs in backup')
    submit = SubmitField('Save Backup Configuration')
