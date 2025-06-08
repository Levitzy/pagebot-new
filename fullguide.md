# Complete Flask Project Deployment Guide for Debian VPS

## Table of Contents
1. [Server Setup](#1-server-setup)
2. [Project Deployment](#2-project-deployment)
3. [Web Server Configuration](#3-web-server-configuration)
4. [SSL Certificate Setup (Optional)](#4-ssl-certificate-setup-optional)
5. [Security Configuration](#5-security-configuration)
6. [Management & Monitoring](#6-management--monitoring)
7. [Multiple Projects Setup](#7-multiple-projects-setup)
8. [Troubleshooting](#8-troubleshooting)

---

## 1. Server Setup

### Initial Server Configuration

#### Update System
```bash
# Update package lists and upgrade system
sudo apt update && sudo apt upgrade -y

# Install essential packages
sudo apt install -y python3 python3-pip python3-venv git nginx supervisor ufw curl wget
```

#### Create User for Your Project
```bash
# Create new user (replace 'myproject' with your project name)
sudo adduser myprojectuser

# Add user to sudo group (optional)
sudo usermod -aG sudo myprojectuser

# Switch to new user
sudo su - myprojectuser
```

#### Setup SSH Key Access (Recommended)
```bash
# On your local computer, generate SSH key
ssh-keygen -t ed25519 -C "your-email@example.com"

# Copy public key to server
ssh-copy-id myprojectuser@your-server-ip

# Or manually add to authorized_keys
mkdir -p ~/.ssh
nano ~/.ssh/authorized_keys
# Paste your public key here
chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys
```

---

## 2. Project Deployment

### Clone and Setup Your Flask Project

#### Method A: From GitHub Repository
```bash
# As your project user
cd /home/myprojectuser
git clone https://github.com/yourusername/your-flask-project.git
cd your-flask-project
```

#### Method B: Upload Local Project
```bash
# From your local computer
scp -r /path/to/your/project myprojectuser@your-server-ip:/home/myprojectuser/

# Or use rsync
rsync -avz /path/to/your/project/ myprojectuser@your-server-ip:/home/myprojectuser/your-flask-project/
```

### Setup Python Environment

#### Create Virtual Environment
```bash
# Navigate to project directory
cd /home/myprojectuser/your-flask-project

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip
```

#### Install Dependencies
```bash
# If you have requirements.txt
pip install -r requirements.txt

# Essential packages for production
pip install gunicorn flask

# Common Flask packages you might need
pip install flask-cors flask-sqlalchemy python-dotenv requests beautifulsoup4 lxml
```

#### Test Your Application
```bash
# Test if your Flask app runs
python app.py  # or your main Flask file
# Press Ctrl+C to stop

# If your app runs on a different file or variable:
# python main.py
# python server.py
```

### Create Gunicorn Configuration

#### Create Gunicorn Startup Script
```bash
nano /home/myprojectuser/your-flask-project/gunicorn_start.sh
```

Add this content (adjust app filename and variable as needed):
```bash
#!/bin/bash
NAME="your-flask-project"
PROJECTDIR=/home/myprojectuser/your-flask-project
SOCKFILE=/home/myprojectuser/your-flask-project/run/gunicorn.sock
USER=myprojectuser
GROUP=myprojectuser
NUM_WORKERS=3

echo "Starting $NAME as `whoami`"

# Change to project directory
cd $PROJECTDIR

# Activate virtual environment
source venv/bin/activate

# Set Python path
export PYTHONPATH=$PROJECTDIR:$PYTHONPATH

# Create run directory
RUNDIR=$(dirname $SOCKFILE)
test -d $RUNDIR || mkdir -p $RUNDIR

# Remove old socket file
test -f $SOCKFILE && rm $SOCKFILE

# Start Gunicorn
# Adjust 'app:app' based on your Flask setup:
# - If your file is app.py with variable 'app': app:app
# - If your file is main.py with variable 'app': main:app
# - If your file is server.py with variable 'app': server:app
# - If your variable is 'application': app:application
exec venv/bin/gunicorn app:app \
  --name $NAME \
  --workers $NUM_WORKERS \
  --user=$USER \
  --group=$GROUP \
  --bind=unix:$SOCKFILE \
  --log-level=info \
  --log-file=-
```

#### Make Script Executable
```bash
chmod +x /home/myprojectuser/your-flask-project/gunicorn_start.sh
mkdir -p /home/myprojectuser/your-flask-project/run
```

---

## 3. Web Server Configuration

### Setup Supervisor (Process Manager)

#### Create Supervisor Configuration
```bash
sudo nano /etc/supervisor/conf.d/your-flask-project.conf
```

Add this content:
```ini
[program:your-flask-project]
command = /home/myprojectuser/your-flask-project/gunicorn_start.sh
user = myprojectuser
stdout_logfile = /var/log/your-flask-project.log
redirect_stderr = true
environment=LANG=en_US.UTF-8,LC_ALL=en_US.UTF-8
autostart=true
autorestart=true
```

#### Start the Service
```bash
# Update supervisor
sudo supervisorctl reread
sudo supervisorctl update

# Start your service
sudo supervisorctl start your-flask-project

# Check status
sudo supervisorctl status
```

### Setup Nginx (Web Server)

#### Create Nginx Configuration
```bash
sudo nano /etc/nginx/sites-available/your-flask-project
```

**Option A: Basic HTTP Configuration**
```nginx
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;  # Replace with your domain or IP
    
    # Security headers
    add_header X-Frame-Options DENY always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    # Hide Nginx version
    server_tokens off;
    
    # Logging
    access_log /var/log/nginx/your-flask-project_access.log;
    error_log /var/log/nginx/your-flask-project_error.log;
    
    client_max_body_size 4M;

    # Block common attack patterns
    location ~* /(wp-admin|wp-login|phpmyadmin|admin|login|xmlrpc) {
        deny all;
        return 404;
    }
    
    # Block sensitive file extensions
    location ~* \.(env|git|sql|log|ini|conf)$ {
        deny all;
        return 404;
    }

    # Static files (if your Flask app serves static files)
    location /static/ {
        alias /home/myprojectuser/your-flask-project/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Main application
    location / {
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_redirect off;
        proxy_buffering off;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;

        proxy_pass http://unix:/home/myprojectuser/your-flask-project/run/gunicorn.sock;
    }
}
```

**Option B: Multiple Projects on Same Server**
```nginx
# For subdirectory access: your-domain.com/projectname/
server {
    listen 80;
    server_name your-domain.com;
    
    # Main site
    location / {
        proxy_pass http://unix:/home/mainuser/main-project/run/gunicorn.sock;
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # Project 1
    location /project1/ {
        rewrite ^/project1/(.*) /$1 break;
        proxy_pass http://unix:/home/user1/project1/run/gunicorn.sock;
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # Project 2
    location /project2/ {
        rewrite ^/project2/(.*) /$1 break;
        proxy_pass http://unix:/home/user2/project2/run/gunicorn.sock;
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

#### Enable the Site
```bash
# Enable your site
sudo ln -s /etc/nginx/sites-available/your-flask-project /etc/nginx/sites-enabled/

# Remove default site (optional)
sudo rm /etc/nginx/sites-enabled/default

# Test Nginx configuration
sudo nginx -t

# If test passes, restart Nginx
sudo systemctl restart nginx
```

### Configure Firewall

#### Setup UFW Firewall
```bash
# Set default policies
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow SSH (important!)
sudo ufw allow ssh

# Allow HTTP and HTTPS
sudo ufw allow 'Nginx Full'

# Or allow specific ports
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Enable firewall
sudo ufw --force enable

# Check status
sudo ufw status
```

---

## 4. SSL Certificate Setup (Optional)

### Method A: Let's Encrypt (Free SSL)

#### Install Certbot
```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx -y
```

#### Get SSL Certificate
```bash
# Get certificate (replace with your domain)
sudo certbot --nginx -d your-domain.com -d www.your-domain.com

# Follow the prompts:
# 1. Enter email address
# 2. Agree to terms of service
# 3. Choose whether to share email with EFF
# 4. Choose redirect option (recommended: 2 - redirect HTTP to HTTPS)
```

#### Auto-renewal Setup
```bash
# Test renewal
sudo certbot renew --dry-run

# Check if auto-renewal timer is active
sudo systemctl status certbot.timer

# If not active, enable it
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer
```

### Method B: Manual HTTPS Configuration

If you have your own SSL certificates:

```bash
sudo nano /etc/nginx/sites-available/your-flask-project
```

Add HTTPS configuration:
```nginx
# HTTP redirect to HTTPS
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;
    return 301 https://your-domain.com$request_uri;
}

# HTTPS server
server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    # SSL Configuration
    ssl_certificate /path/to/your/certificate.crt;
    ssl_certificate_key /path/to/your/private.key;
    
    # Modern SSL settings
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    
    # Security headers
    add_header Strict-Transport-Security "max-age=63072000" always;
    add_header X-Frame-Options DENY always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;
    
    # Your Flask application configuration (same as HTTP version)
    location / {
        proxy_pass http://unix:/home/myprojectuser/your-flask-project/run/gunicorn.sock;
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 5. Security Configuration

### Setup Fail2Ban (Brute Force Protection)

#### Install and Configure Fail2Ban
```bash
# Install fail2ban
sudo apt install fail2ban -y

# Create local configuration
sudo cp /etc/fail2ban/jail.conf /etc/fail2ban/jail.local

# Edit configuration
sudo nano /etc/fail2ban/jail.local
```

Add at the end:
```ini
[sshd]
enabled = true
port = ssh
maxretry = 3
bantime = 3600

[nginx-http-auth]
enabled = true
filter = nginx-http-auth
port = http,https
logpath = /var/log/nginx/error.log
maxretry = 3
bantime = 3600

[nginx-your-flask-project]
enabled = true
port = http,https
filter = nginx-your-flask-project
logpath = /var/log/nginx/your-flask-project_access.log
maxretry = 10
bantime = 3600
```

#### Create Custom Filter
```bash
sudo nano /etc/fail2ban/filter.d/nginx-your-flask-project.conf
```

Add:
```ini
[Definition]
failregex = ^<HOST> -.*"(GET|POST|HEAD).*HTTP.*" (4|5)\d\d
            ^<HOST> -.*".*sqlmap.*"
            ^<HOST> -.*".*union.*select.*"
ignoreregex =
```

#### Start Fail2Ban
```bash
sudo systemctl enable fail2ban
sudo systemctl start fail2ban

# Check status
sudo fail2ban-client status
```

### SSH Security Hardening

#### Secure SSH Configuration
```bash
sudo nano /etc/ssh/sshd_config
```

Recommended settings:
```bash
# Change default port (optional but recommended)
Port 2222

# Disable root login
PermitRootLogin no

# Disable password authentication (use SSH keys only)
PasswordAuthentication no
PubkeyAuthentication yes

# Limit login attempts
MaxAuthTries 3
MaxStartups 3

# Set login timeout
LoginGraceTime 30

# Allow specific users only
AllowUsers myprojectuser

# Disable X11 forwarding
X11Forwarding no
```

#### Restart SSH (Make sure you have SSH key access first!)
```bash
sudo systemctl restart sshd

# Update firewall for new SSH port (if changed)
sudo ufw delete allow ssh
sudo ufw allow 2222/tcp
```

---

## 6. Management & Monitoring

### Project Update Process

When you update your project on GitHub and need to deploy changes to your server, follow this process:

#### Manual Update Process
```bash
# 1. Switch to project user
sudo su - myprojectuser

# 2. Navigate to project directory
cd /home/myprojectuser/your-flask-project

# 3. Check current status
git status
git log --oneline -5  # See recent commits

# 4. Pull latest changes from GitHub
git pull origin main

# 5. Activate virtual environment
source venv/bin/activate

# 6. Update dependencies (if requirements.txt changed)
pip install -r requirements.txt

# 7. Exit back to main user
exit

# 8. Restart the application service
sudo supervisorctl restart your-flask-project

# 9. Check if service is running properly
sudo supervisorctl status your-flask-project

# 10. Test the application
curl -I http://your-domain.com  # or your actual URL
```

#### Create Automated Update Script
```bash
nano /home/myprojectuser/update_project.sh
```

Add this comprehensive update script:
```bash
#!/bin/bash
set -e  # Exit on any error

PROJECT_NAME="your-flask-project"
PROJECT_DIR="/home/myprojectuser/your-flask-project"
PROJECT_USER="myprojectuser"

echo "========================================="
echo "Starting update for $PROJECT_NAME"
echo "========================================="

# Check if we're running as the correct user
if [ "$USER" != "$PROJECT_USER" ]; then
    echo "Error: This script should be run as $PROJECT_USER"
    echo "Run: sudo su - $PROJECT_USER"
    exit 1
fi

# Navigate to project directory
cd $PROJECT_DIR

# Show current status
echo "Current branch and status:"
git branch --show-current
git status --porcelain

# Stash any local changes (optional - be careful!)
if [ ! -z "$(git status --porcelain)" ]; then
    echo "Warning: Local changes detected. Stashing them..."
    git stash push -m "Auto-stash before update $(date)"
fi

# Pull latest changes
echo "Pulling latest changes from GitHub..."
git fetch origin
git pull origin main

# Show what changed
echo "Recent commits:"
git log --oneline -5

# Check if requirements.txt was modified
if git diff HEAD~1 --name-only | grep -q "requirements.txt"; then
    echo "requirements.txt was modified. Updating dependencies..."
    
    # Activate virtual environment
    source venv/bin/activate
    
    # Update pip first
    pip install --upgrade pip
    
    # Install/update dependencies
    pip install -r requirements.txt
    
    echo "Dependencies updated successfully."
else
    echo "No changes to requirements.txt detected."
fi

# Check if there are any Python syntax errors
echo "Checking for Python syntax errors..."
python3 -m py_compile app.py  # Replace with your main Flask file

echo "Update preparation completed successfully!"
echo ""
echo "Next steps:"
echo "1. Exit to main user: exit"
echo "2. Restart service: sudo supervisorctl restart $PROJECT_NAME"
echo "3. Check status: sudo supervisorctl status $PROJECT_NAME"
echo "4. Test application: curl -I http://your-domain.com"
```

Make the script executable:
```bash
chmod +x /home/myprojectuser/update_project.sh
```

#### Create Complete Update Script (Advanced)
For a fully automated update process:

```bash
nano /home/myprojectuser/full_update.sh
```

Add:
```bash
#!/bin/bash
set -e

PROJECT_NAME="your-flask-project"
PROJECT_DIR="/home/myprojectuser/your-flask-project"
PROJECT_USER="myprojectuser"
MAIN_USER="$(logname 2>/dev/null || echo $SUDO_USER)"

echo "========================================="
echo "Full automated update for $PROJECT_NAME"
echo "========================================="

# Function to run commands as project user
run_as_project_user() {
    sudo -u $PROJECT_USER bash -c "cd $PROJECT_DIR && $1"
}

# Function to check service health
check_service_health() {
    echo "Checking service health..."
    if sudo supervisorctl status $PROJECT_NAME | grep -q "RUNNING"; then
        echo "✓ Service is running"
        
        # Test HTTP response
        if curl -s -o /dev/null -w "%{http_code}" http://localhost | grep -q "200\|301\|302"; then
            echo "✓ Application responding correctly"
            return 0
        else
            echo "✗ Application not responding correctly"
            return 1
        fi
    else
        echo "✗ Service is not running"
        return 1
    fi
}

# Backup current state
echo "Creating backup..."
BACKUP_DIR="/home/$PROJECT_USER/backups"
run_as_project_user "mkdir -p $BACKUP_DIR"
run_as_project_user "git bundle create $BACKUP_DIR/backup-$(date +%Y%m%d-%H%M%S).bundle --all"

# Update code
echo "Updating code from GitHub..."
run_as_project_user "git fetch origin"
run_as_project_user "git pull origin main"

# Check for dependency changes
if run_as_project_user "git diff HEAD~1 --name-only | grep -q requirements.txt" 2>/dev/null; then
    echo "Updating dependencies..."
    run_as_project_user "source venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt"
fi

# Restart service
echo "Restarting application service..."
sudo supervisorctl restart $PROJECT_NAME

# Wait for service to start
sleep 3

# Health check
if check_service_health; then
    echo ""
    echo "========================================="
    echo "✓ Update completed successfully!"
    echo "========================================="
    echo "Service: $(sudo supervisorctl status $PROJECT_NAME)"
    echo "Recent commits:"
    run_as_project_user "git log --oneline -3"
else
    echo ""
    echo "========================================="
    echo "✗ Update completed but service issues detected!"
    echo "========================================="
    echo "Check logs: sudo tail -20 /var/log/$PROJECT_NAME.log"
    exit 1
fi
```

Make executable:
```bash
chmod +x /home/myprojectuser/full_update.sh
```

#### Usage Examples

**Simple update (manual steps):**
```bash
# As project user
sudo su - myprojectuser
./update_project.sh
exit

# As main user
sudo supervisorctl restart your-flask-project
sudo supervisorctl status
```

**Automated update (one command):**
```bash
# As main user with sudo access
/home/myprojectuser/full_update.sh
```

**Quick restart after git pull:**
```bash
# If you already did git pull manually
sudo supervisorctl restart your-flask-project
sudo supervisorctl status your-flask-project

# Check if changes applied
curl -I http://your-domain.com
```

#### Common Update Scenarios

**Scenario 1: Code changes only**
```bash
sudo su - myprojectuser
cd your-flask-project
git pull origin main
exit
sudo supervisorctl restart your-flask-project
```

**Scenario 2: New dependencies added**
```bash
sudo su - myprojectuser
cd your-flask-project
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
exit
sudo supervisorctl restart your-flask-project
```

**Scenario 3: Configuration changes**
```bash
sudo su - myprojectuser
cd your-flask-project
git pull origin main
exit
sudo supervisorctl restart your-flask-project
sudo systemctl reload nginx  # If nginx config changed
```

**Scenario 4: Database migrations (if using Flask-SQLAlchemy)**
```bash
sudo su - myprojectuser
cd your-flask-project
git pull origin main
source venv/bin/activate
flask db upgrade  # or python migrations/upgrade.py
exit
sudo supervisorctl restart your-flask-project
```

#### Troubleshooting Updates

**If git pull fails:**
```bash
# Check for merge conflicts
git status

# See what files are conflicting
git diff

# Reset to remote version (careful - loses local changes!)
git reset --hard origin/main

# Or stash local changes first
git stash
git pull origin main
```

**If service won't restart:**
```bash
# Check what's wrong
sudo supervisorctl tail your-flask-project

# Check Python syntax
sudo su - myprojectuser
cd your-flask-project
source venv/bin/activate
python -m py_compile app.py

# Check for missing dependencies
pip check
```

**If application shows errors after update:**
```bash
# Check application logs
sudo tail -50 /var/log/your-flask-project.log

# Check nginx logs
sudo tail -20 /var/log/nginx/error.log

# Roll back to previous version
sudo su - myprojectuser
cd your-flask-project
git log --oneline -10  # Find previous commit
git reset --hard COMMIT_HASH
exit
sudo supervisorctl restart your-flask-project
```

#### Update Checklist

Before updating:
- [ ] Check current application status
- [ ] Backup current code state
- [ ] Test in development environment
- [ ] Plan for downtime (if any)

During update:
- [ ] Pull latest changes
- [ ] Update dependencies if needed
- [ ] Check for configuration changes
- [ ] Restart services
- [ ] Verify application health

After update:
- [ ] Test main functionality
- [ ] Check error logs
- [ ] Monitor performance
- [ ] Validate all features work

#### Monitoring Recent Changes

```bash
# See what changed in last update
sudo su - myprojectuser
cd your-flask-project

# Show recent commits
git log --oneline -10

# Show files changed in last commit
git show --name-only

# Show detailed changes
git show

# Compare with previous version
git diff HEAD~1 HEAD
```

### Monitoring Commands

#### Check Service Status
```bash
# Check all services
sudo supervisorctl status

# Check specific service
sudo supervisorctl status your-flask-project

# Check Nginx
sudo systemctl status nginx

# Check if ports are listening
sudo netstat -tulpn | grep -E ':80|:443'
```

#### View Logs
```bash
# Application logs
sudo tail -f /var/log/your-flask-project.log

# Nginx access logs
sudo tail -f /var/log/nginx/your-flask-project_access.log

# Nginx error logs
sudo tail -f /var/log/nginx/error.log

# System logs
sudo journalctl -f
```

#### Restart Services
```bash
# Restart Flask application
sudo supervisorctl restart your-flask-project

# Restart Nginx
sudo systemctl restart nginx

# Restart supervisor
sudo systemctl restart supervisor
```

---

## 7. Multiple Projects Setup

### Adding Additional Flask Projects

#### For Each New Project:

1. **Create new user:**
```bash
sudo adduser newprojectuser
```

2. **Deploy project:**
```bash
sudo su - newprojectuser
git clone https://github.com/yourusername/new-project.git
cd new-project
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install gunicorn
```

3. **Create Gunicorn script and Supervisor config** (follow steps from section 2)

4. **Add to Nginx configuration:**

**Option A: Subdirectory Access**
```nginx
# Add to existing server block
location /newproject/ {
    rewrite ^/newproject/(.*) /$1 break;
    proxy_pass http://unix:/home/newprojectuser/new-project/run/gunicorn.sock;
    proxy_set_header Host $http_host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

**Option B: Different Port**
```nginx
server {
    listen 8080;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://unix:/home/newprojectuser/new-project/run/gunicorn.sock;
        # ... other proxy settings
    }
}
```

**Option C: Subdomain** (requires DNS setup)
```nginx
server {
    listen 80;
    server_name newproject.your-domain.com;
    
    location / {
        proxy_pass http://unix:/home/newprojectuser/new-project/run/gunicorn.sock;
        # ... other proxy settings
    }
}
```

### Project URLs Structure Examples

#### Subdirectory Setup:
- Main site: `https://your-domain.com/`
- Project 1: `https://your-domain.com/api/`
- Project 2: `https://your-domain.com/dashboard/`
- Project 3: `https://your-domain.com/admin/`

#### Port-based Setup:
- Main site: `https://your-domain.com/` (port 443)
- Project 1: `https://your-domain.com:8080/`
- Project 2: `https://your-domain.com:8081/`

#### Subdomain Setup:
- Main site: `https://your-domain.com/`
- Project 1: `https://api.your-domain.com/`
- Project 2: `https://dashboard.your-domain.com/`

---

## 8. Troubleshooting

### Common Issues and Solutions

#### Service Won't Start
```bash
# Check supervisor logs
sudo supervisorctl tail your-flask-project

# Check application logs
sudo tail -20 /var/log/your-flask-project.log

# Test Gunicorn manually
sudo su - myprojectuser
cd /home/myprojectuser/your-flask-project
source venv/bin/activate
./gunicorn_start.sh
```

#### 502 Bad Gateway Error
```bash
# Check if service is running
sudo supervisorctl status your-flask-project

# Check socket file exists
ls -la /home/myprojectuser/your-flask-project/run/

# Remove stuck socket file and restart
sudo rm -f /home/myprojectuser/your-flask-project/run/gunicorn.sock
sudo supervisorctl restart your-flask-project
```

#### Permission Issues
```bash
# Fix file ownership
sudo chown -R myprojectuser:myprojectuser /home/myprojectuser/your-flask-project

# Fix socket directory permissions
sudo chmod 755 /home/myprojectuser/your-flask-project/run/
```

#### Nginx Configuration Errors
```bash
# Test Nginx configuration
sudo nginx -t

# Check Nginx error logs
sudo tail -20 /var/log/nginx/error.log

# Restart Nginx
sudo systemctl restart nginx
```

#### SSL Certificate Issues
```bash
# Check certificate status
sudo certbot certificates

# Renew certificate manually
sudo certbot renew --force-renewal

# Check certificate files exist
sudo ls -la /etc/letsencrypt/live/your-domain.com/
```

### Diagnostic Commands

#### System Resources
```bash
# Check disk space
df -h

# Check memory usage
free -h

# Check CPU usage
top

# Check running processes
ps aux | grep -E 'nginx|gunicorn|supervisor'
```

#### Network Diagnostics
```bash
# Check listening ports
sudo ss -tulpn

# Test connectivity
curl -I http://localhost
curl -I https://your-domain.com

# Check DNS resolution
nslookup your-domain.com
```

#### Log Analysis
```bash
# Check recent errors
sudo grep -i error /var/log/nginx/error.log | tail -10
sudo grep -i error /var/log/your-flask-project.log | tail -10

# Monitor logs in real-time
sudo tail -f /var/log/nginx/your-flask-project_access.log
```

---

## Quick Deployment Checklist

### Pre-deployment:
- [ ] Server updated and secured
- [ ] User created for project
- [ ] SSH key access configured
- [ ] Firewall configured

### Deployment:
- [ ] Project code uploaded/cloned
- [ ] Virtual environment created
- [ ] Dependencies installed
- [ ] Gunicorn script configured
- [ ] Supervisor service created and started
- [ ] Nginx site configured and enabled
- [ ] Firewall rules updated

### Post-deployment:
- [ ] SSL certificate installed (if needed)
- [ ] Fail2Ban configured
- [ ] Monitoring scripts created
- [ ] Backup strategy implemented
- [ ] Update procedures documented

### Testing:
- [ ] Application loads correctly
- [ ] All routes/endpoints work
- [ ] Static files serve properly
- [ ] HTTPS redirect works (if using SSL)
- [ ] Security headers present
- [ ] Performance acceptable

---

## Summary

This guide covers the complete process of deploying Flask applications on a Debian VPS, from initial server setup to production deployment with optional SSL certificates. The configuration is production-ready with security best practices, monitoring, and maintenance procedures.

Key components deployed:
- **Flask Application** (your Python code)
- **Gunicorn** (WSGI server)
- **Supervisor** (process manager)
- **Nginx** (web server/reverse proxy)
- **SSL/TLS** (optional encryption)
- **Fail2Ban** (security)
- **UFW** (firewall)

Your Flask application will be accessible, secure, and maintainable with this setup!