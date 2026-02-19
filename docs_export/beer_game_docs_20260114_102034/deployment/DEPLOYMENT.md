# Production Deployment Guide

Complete guide for deploying The Beer Game platform to staging and production environments.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Environment Configuration](#environment-configuration)
3. [Deployment Process](#deployment-process)
4. [Health Checks](#health-checks)
5. [Rollback Procedures](#rollback-procedures)
6. [Monitoring](#monitoring)
7. [Troubleshooting](#troubleshooting)

## Prerequisites

### Required Software

- Docker 20.10+
- Docker Compose 2.0+
- MySQL/MariaDB client tools
- curl
- bash 4.0+

### Access Requirements

- SSH access to deployment servers
- Docker registry credentials
- Database credentials
- SSL certificates (for production)

### Environment Variables

Required environment variables in `.env`:

```env
# Environment
ENVIRONMENT=production  # or staging

# Database
MARIADB_HOST=db
MARIADB_DATABASE=beer_game
MARIADB_USER=beer_user
MARIADB_PASSWORD=<secure_password>
MARIADB_ROOT_PASSWORD=<secure_root_password>

# Security
SECRET_KEY=<generated_secret_key>
SECRETS_ENCRYPTION_KEY=<generated_encryption_key>

# OpenAI (optional)
OPENAI_API_KEY=sk-...
OPENAI_PROJECT=proj_...
GPT_ID=g-...

# Application
CORS_ORIGINS=https://autonomy.com
ALLOWED_HOSTS=autonomy.com
```

## Environment Configuration

### Development

```bash
# Use development configuration
export ENVIRONMENT=development
make up-dev
```

### Staging

```bash
# Use staging configuration
export ENVIRONMENT=staging
./deploy/deploy.sh staging
```

### Production

```bash
# Use production configuration
export ENVIRONMENT=production
./deploy/deploy.sh production
```

## Deployment Process

### Standard Deployment

```bash
# Deploy to staging
./deploy/deploy.sh staging

# Deploy to production
./deploy/deploy.sh production
```

### Deployment Steps

The deployment script performs the following steps:

1. **Backup Current Deployment**
   - Backs up docker-compose files
   - Exports current Docker images
   - Dumps database to SQL file
   - Creates versioned backup directory

2. **Pull/Build Images**
   - Pulls latest images from registry
   - Or builds images locally

3. **Stop Current Containers**
   - Gracefully stops all running containers
   - Preserves volumes

4. **Start New Containers**
   - Starts containers with new images
   - Uses docker-compose.prod.yml overlay

5. **Run Database Migrations**
   - Executes Alembic migrations
   - Upgrades schema to latest version

6. **Validate Deployment**
   - Health check endpoints
   - Database connectivity
   - Smoke tests

7. **Rollback on Failure**
   - Automatically rolls back if validation fails
   - Restores previous version

### Deployment Validation

The deployment script validates:

- **Backend Health**: `/api/v1/health/ready` returns 200
- **Database Connectivity**: Can execute queries
- **Smoke Tests**: Basic functionality tests pass

### Manual Deployment Steps

If you need to deploy manually:

```bash
# 1. Backup database
docker compose exec db mysqldump -u root -p beer_game > backup.sql

# 2. Pull latest changes
git pull origin main

# 3. Build images
docker compose -f docker-compose.yml -f docker-compose.prod.yml build

# 4. Stop containers
docker compose -f docker-compose.yml -f docker-compose.prod.yml down

# 5. Start containers
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# 6. Run migrations
docker compose exec backend alembic upgrade head

# 7. Verify deployment
curl http://localhost:8000/api/v1/health/ready
```

## Health Checks

### Liveness Probe

Checks if the application is running:

```bash
curl http://localhost:8000/api/v1/health/live
```

Response:
```json
{
  "status": "healthy",
  "timestamp": "2026-01-14T10:00:00Z"
}
```

### Readiness Probe

Checks if the application is ready to serve traffic:

```bash
curl http://localhost:8000/api/v1/health/ready
```

Response:
```json
{
  "status": "healthy",
  "components": {
    "database": "healthy",
    "cache": "healthy"
  },
  "timestamp": "2026-01-14T10:00:00Z"
}
```

### Detailed Health Check

Comprehensive health information:

```bash
curl http://localhost:8000/api/v1/health/detailed
```

Response includes:
- Component-level health status
- Response times
- Resource usage
- Error counts

### Kubernetes Health Probes

```yaml
livenessProbe:
  httpGet:
    path: /api/v1/health/live
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /api/v1/health/ready
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 5
  timeoutSeconds: 3
  failureThreshold: 3
```

## Rollback Procedures

### Automatic Rollback

The deployment script automatically rolls back on validation failure.

### Manual Rollback

List available backups:

```bash
ls -1 backups/
```

Rollback to specific version:

```bash
./deploy/rollback.sh production backup_production_20260114_100000
```

### Rollback Steps

1. Stop current containers
2. Load backup Docker images
3. Restore database from backup
4. Start containers with previous version
5. Verify rollback successful

### Emergency Rollback

If automated rollback fails:

```bash
# 1. Stop all containers
docker compose down

# 2. Restore database manually
docker compose up -d db
mysql -u root -p beer_game < backups/backup_XXX/database.sql

# 3. Load previous images
docker load -i backups/backup_XXX/backend.tar
docker load -i backups/backup_XXX/frontend.tar

# 4. Start containers
docker compose up -d
```

### Rollback Testing

Test rollback procedure in staging:

```bash
# Deploy version 1
./deploy/deploy.sh staging v1

# Deploy version 2
./deploy/deploy.sh staging v2

# Rollback to version 1
ls backups/  # Find v1 backup
./deploy/rollback.sh staging backup_staging_YYYYMMDD_HHMMSS
```

## Monitoring

### Application Metrics

Prometheus metrics endpoint:

```bash
curl http://localhost:8000/api/v1/metrics
```

Key metrics:
- `http_requests_total`: Total HTTP requests
- `http_request_duration_seconds`: Request duration histogram
- `http_requests_in_progress`: Concurrent requests
- `database_connections`: Active DB connections
- `cache_hits_total`: Cache hit count

### JSON Metrics

JSON-formatted metrics:

```bash
curl http://localhost:8000/api/v1/metrics/json
```

### Log Monitoring

View application logs:

```bash
# All logs
docker compose logs -f

# Backend only
docker compose logs -f backend

# Last 100 lines
docker compose logs --tail=100 backend
```

### Database Monitoring

Monitor database:

```bash
# Connection count
docker compose exec db mysql -u root -p -e "SHOW PROCESSLIST;"

# Database size
docker compose exec db mysql -u root -p -e "
  SELECT
    table_schema AS 'Database',
    ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) AS 'Size (MB)'
  FROM information_schema.tables
  WHERE table_schema = 'beer_game'
  GROUP BY table_schema;
"
```

### Resource Monitoring

```bash
# Container stats
docker stats

# Disk usage
docker system df

# Network usage
docker network inspect beer_game_default
```

## Troubleshooting

### Deployment Fails at Migration Step

**Problem**: Database migration fails during deployment

**Solution**:
```bash
# Check migration status
docker compose exec backend alembic current

# View migration history
docker compose exec backend alembic history

# Manually run migrations
docker compose exec backend alembic upgrade head

# Rollback specific migration
docker compose exec backend alembic downgrade -1
```

### Health Check Fails

**Problem**: Health check endpoint returns unhealthy status

**Solution**:
```bash
# Check detailed health
curl http://localhost:8000/api/v1/health/detailed

# Check logs for errors
docker compose logs --tail=100 backend

# Verify database connectivity
docker compose exec backend python -c "
from app.db.session import SessionLocal
db = SessionLocal()
print(db.execute('SELECT 1').scalar())
"
```

### Database Connection Errors

**Problem**: Cannot connect to database

**Solution**:
```bash
# Verify database is running
docker compose ps db

# Check database logs
docker compose logs db

# Test connection
mysql -h localhost -P 3306 -u beer_user -p

# Verify credentials in .env
cat .env | grep MARIADB
```

### Port Already in Use

**Problem**: Port 8000 or 3000 already in use

**Solution**:
```bash
# Find process using port
lsof -i :8000
lsof -i :3000

# Kill process
kill -9 <PID>

# Or change port in docker-compose.yml
```

### Docker Disk Space Issues

**Problem**: No space left on device

**Solution**:
```bash
# Clean up unused images
docker image prune -a

# Clean up volumes
docker volume prune

# Clean up everything
docker system prune -a --volumes

# Check disk usage
docker system df
```

### SSL Certificate Issues

**Problem**: SSL certificate expired or invalid

**Solution**:
```bash
# Check certificate expiry
openssl x509 -in /path/to/cert.pem -noout -dates

# Renew Let's Encrypt certificate
certbot renew

# Update certificate in nginx
cp /etc/letsencrypt/live/domain/fullchain.pem /path/to/certs/
cp /etc/letsencrypt/live/domain/privkey.pem /path/to/certs/
docker compose restart proxy
```

## Best Practices

### Pre-Deployment Checklist

- [ ] Backup current deployment
- [ ] Test in staging environment
- [ ] Review database migrations
- [ ] Update documentation
- [ ] Notify team of deployment window
- [ ] Prepare rollback plan

### Post-Deployment Checklist

- [ ] Verify health checks passing
- [ ] Monitor application logs
- [ ] Check error rates in metrics
- [ ] Test critical user workflows
- [ ] Monitor performance
- [ ] Update deployment log

### Deployment Schedule

- **Staging**: Deploy anytime
- **Production**: Deploy during maintenance window
  - Preferred: Tuesday/Thursday 2-4 AM UTC
  - Avoid: Fridays, holidays, peak usage times

### Zero-Downtime Deployment

For zero-downtime deployments:

1. Use blue-green deployment strategy
2. Run new version alongside old
3. Switch traffic after validation
4. Keep old version running for quick rollback

## Security Considerations

### Secrets Management

- Never commit secrets to git
- Use environment variables
- Encrypt secrets at rest
- Rotate secrets regularly

### SSL/TLS

- Use valid SSL certificates
- Enable HSTS headers
- Enforce HTTPS in production
- Use strong cipher suites

### Access Control

- Limit SSH access
- Use SSH keys, not passwords
- Enable MFA for critical systems
- Audit access logs regularly

## Support

For deployment issues:

1. Check this documentation
2. Review application logs
3. Check monitoring dashboards
4. Contact DevOps team

## References

- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Alembic Migration Guide](https://alembic.sqlalchemy.org/)
- [FastAPI Deployment](https://fastapi.tiangolo.com/deployment/)
- [Nginx Configuration](https://nginx.org/en/docs/)
