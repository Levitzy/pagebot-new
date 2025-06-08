# Complete Server Management Guide - Nginx & Supervisor Commands

## Quick Project Update Process

### When you update your project with `git pull`:
```bash
# 1. Pull latest changes (as project user)
sudo su - biarpagebot  # or gaguser for gagv2
cd /home/biarpagebot/pagebot-new  # or /home/gaguser/gagv2
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
exit

# 2. Restart application service
sudo supervisorctl restart pagebot-new  # or gagv2

# 3. Check if running
sudo supervisorctl status
```

## Nginx Management Commands

### Basic Nginx Control
```bash
# Start Nginx
sudo systemctl start nginx

# Stop Nginx
sudo systemctl stop nginx

# Restart Nginx (Stop + Start)
sudo systemctl restart nginx

# Reload Configuration (No Downtime - Recommended)
sudo systemctl reload nginx

# Check Status
sudo systemctl status nginx

# Test Configuration (Always do this before reload/restart)
sudo nginx -t

# Safe Reload (Test first, then reload only if valid)
sudo nginx -t && sudo systemctl reload nginx
```

### Nginx Site Management
```bash
# List available sites
ls -la /etc/nginx/sites-available/

# List enabled sites
ls -la /etc/nginx/sites-enabled/

# Enable a site
sudo ln -s /etc/nginx/sites-available/sitename /etc/nginx/sites-enabled/

# Disable a site
sudo rm /etc/nginx/sites-enabled/sitename

# Edit site configuration
sudo nano /etc/nginx/sites-available/gagv2
sudo nano /etc/nginx/sites-available/pagebot-new

# After any config change, always:
sudo nginx -t && sudo systemctl reload nginx
```

### Nginx Log Management
```bash
# View real-time logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
sudo tail -f /var/log/nginx/gagv2_access.log
sudo tail -f /var/log/nginx/pagebot_access.log

# View recent log entries
sudo tail -20 /var/log/nginx/error.log
sudo tail -50 /var/log/nginx/gagv2_access.log

# Check log file sizes
du -h /var/log/nginx/*
```

## Supervisor Management Commands

### Basic Supervisor Control
```bash
# Check status of all services
sudo supervisorctl status

# Check status of specific service
sudo supervisorctl status gagv2
sudo supervisorctl status pagebot-new

# Start a service
sudo supervisorctl start gagv2
sudo supervisorctl start pagebot-new

# Stop a service
sudo supervisorctl stop gagv2
sudo supervisorctl stop pagebot-new

# Restart a service (Most common after code updates)
sudo supervisorctl restart gagv2
sudo supervisorctl restart pagebot-new

# Restart all services
sudo supervisorctl restart all
```

### Supervisor Configuration Management
```bash
# After adding/modifying supervisor config files
sudo supervisorctl reread     # Read new configuration files
sudo supervisorctl update     # Apply changes
sudo supervisorctl start servicename  # Start new service

# Reload supervisor itself
sudo systemctl restart supervisor

# View supervisor main log
sudo tail -f /var/log/supervisor/supervisord.log
```

### Application Log Management
```bash
# View application logs
sudo tail -f /var/log/gagv2.log
sudo tail -f /var/log/pagebot-new.log

# View recent errors
sudo tail -20 /var/log/gagv2.log
sudo tail -20 /var/log/pagebot-new.log

# Clear logs (if they get too large)
sudo truncate -s 0 /var/log/gagv2.log
sudo truncate -s 0 /var/log/pagebot-new.log
```

## Project Update Workflows

### For PageBot-New Project
```bash
# Method 1: Manual update
sudo su - biarpagebot
cd /home/biarpagebot/pagebot-new
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
exit
sudo supervisorctl restart pagebot-new
sudo supervisorctl status

# Method 2: Using update script (if created)
/home/biarpagebot/update_pagebot.sh
```

### For GagV2 Project
```bash
# Method 1: Manual update
sudo su - gaguser
cd /home/gaguser/gagv2
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
exit
sudo supervisorctl restart gagv2
sudo supervisorctl status

# Method 2: Using update script (if created)
/home/gaguser/update_gagv2.sh
```

### Update Both Projects
```bash
# Quick update both projects
sudo supervisorctl stop all
sudo su - gaguser
cd /home/gaguser/gagv2 && git pull && source venv/bin/activate && pip install -r requirements.txt
exit
sudo su - biarpagebot
cd /home/biarpagebot/pagebot-new && git pull && source venv/bin/activate && pip install -r requirements.txt
exit
sudo supervisorctl start all
sudo supervisorctl status
```

## Service Status Monitoring

### Quick Health Check
```bash
# Check all services at once
sudo supervisorctl status
sudo systemctl status nginx
sudo systemctl status supervisor

# Check if ports are listening
sudo netstat -tulpn | grep -E ':80|:443|:8080|:8443'
sudo ss -tulpn | grep -E ':80|:443'

# Check process usage
ps aux | grep -E 'nginx|gunicorn|supervisor'
top -p $(pgrep -d',' -f 'nginx|gunicorn|supervisor')
```

### Troubleshooting Commands
```bash
# If service won't start
sudo supervisorctl tail gagv2
sudo supervisorctl tail pagebot-new

# Check for socket files
ls -la /home/gaguser/gagv2/run/
ls -la /home/biarpagebot/pagebot-new/run/

# Remove stuck socket files
sudo rm -f /home/gaguser/gagv2/run/gunicorn.sock
sudo rm -f /home/biarpagebot/pagebot-new/run/gunicorn.sock

# Kill stuck processes
sudo pkill -f gagv2
sudo pkill -f pagebot-new
sudo supervisorctl restart all
```

## Security & Maintenance

### Fail2Ban Management
```bash
# Check fail2ban status
sudo fail2ban-client status

# Check specific jails
sudo fail2ban-client status sshd
sudo fail2ban-client status nginx-gagv2
sudo fail2ban-client status nginx-pagebot

# Unban an IP if needed
sudo fail2ban-client set sshd unbanip IP_ADDRESS

# Restart fail2ban
sudo systemctl restart fail2ban
```

### Firewall Management
```bash
# Check firewall status
sudo ufw status

# Allow new ports
sudo ufw allow 8080/tcp
sudo ufw allow 8443/tcp

# Remove port rules
sudo ufw delete allow 8080/tcp

# Reload firewall
sudo ufw reload
```

### SSL Certificate Management
```bash
# Check certificate status
sudo certbot certificates

# Renew certificates
sudo certbot renew

# Test renewal process
sudo certbot renew --dry-run

# Check certificate expiry
sudo openssl x509 -in /etc/letsencrypt/live/vmi2625091.contaboserver.net/fullchain.pem -text -noout | grep -A 2 "Validity"
```

## Quick Reference Cheat Sheet

### Daily Operations
| Task | Command |
|------|---------|
| **Restart app after code update** | `sudo supervisorctl restart servicename` |
| **Check if services running** | `sudo supervisorctl status` |
| **Reload Nginx config** | `sudo nginx -t && sudo systemctl reload nginx` |
| **Check logs** | `sudo tail -f /var/log/servicename.log` |
| **Test Nginx config** | `sudo nginx -t` |

### Emergency Commands
| Problem | Solution |
|---------|----------|
| **Site down** | `sudo systemctl status nginx && sudo supervisorctl status` |
| **502 Bad Gateway** | `sudo supervisorctl restart servicename` |
| **Config error** | `sudo nginx -t` to see error details |
| **Service won't start** | `sudo supervisorctl tail servicename` |
| **Kill stuck processes** | `sudo pkill -f servicename` |

### File Locations
| Type | Location |
|------|----------|
| **Nginx sites** | `/etc/nginx/sites-available/` |
| **Enabled sites** | `/etc/nginx/sites-enabled/` |
| **Supervisor configs** | `/etc/supervisor/conf.d/` |
| **Application logs** | `/var/log/servicename.log` |
| **Nginx logs** | `/var/log/nginx/` |
| **SSL certificates** | `/etc/letsencrypt/live/domain/` |

## Complete Server Restart Sequence

### If you need to restart everything:
```bash
# 1. Stop all services gracefully
sudo supervisorctl stop all
sudo systemctl stop nginx

# 2. Start core services
sudo systemctl start nginx
sudo systemctl start supervisor

# 3. Start applications
sudo supervisorctl start all

# 4. Verify everything is running
sudo systemctl status nginx
sudo supervisorctl status
sudo netstat -tulpn | grep -E ':80|:443'

# 5. Test websites
curl -I https://vmi2625091.contaboserver.net/
curl -I https://vmi2625091.contaboserver.net/pagebot/
```

## Your Current Setup Summary

### Services:
- **gagv2**: Main API service (gaguser)
- **pagebot-new**: PageBot application (biarpagebot)

### URLs:
- **Main API**: `https://vmi2625091.contaboserver.net/`
- **PageBot**: `https://vmi2625091.contaboserver.net/pagebot/`

### Quick Daily Commands:
```bash
# After git pull on any project:
sudo supervisorctl restart projectname

# Check everything is running:
sudo supervisorctl status

# View logs if issues:
sudo tail -f /var/log/projectname.log
```