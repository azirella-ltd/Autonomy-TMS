# API Reference

## Access API Documentation

When the application is running, access interactive API documentation at:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Quick API Examples

### Authentication
```bash
# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -d "username=systemadmin@autonomy.ai&password=Autonomy@2026"

# Get current user
curl -X GET http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Templates
```bash
# List templates
curl http://localhost:8000/api/v1/templates?page=1&page_size=20

# Get featured templates
curl http://localhost:8000/api/v1/templates/featured?limit=5

# Quick start wizard
curl -X POST http://localhost:8000/api/v1/templates/quick-start \
  -H "Content-Type: application/json" \
  -d '{"industry":"retail","difficulty":"beginner","num_players":4}'
```

### Health Checks
```bash
# Liveness probe
curl http://localhost:8000/api/v1/health/live

# Readiness probe
curl http://localhost:8000/api/v1/health/ready

# Detailed health
curl http://localhost:8000/api/v1/health/detailed

# Metrics
curl http://localhost:8000/api/v1/metrics
```

## API Endpoints Summary

### Core Game API
- `POST /api/v1/mixed-games/` - Create new game
- `POST /api/v1/mixed-games/{id}/start` - Start game
- `POST /api/v1/mixed-games/{id}/play-round` - Play round
- `GET /api/v1/mixed-games/{id}/state` - Get game state

### Templates API
- `GET /api/v1/templates` - List templates
- `GET /api/v1/templates/{id}` - Get template
- `POST /api/v1/templates/quick-start` - Quick start wizard
- `GET /api/v1/templates/featured` - Featured templates

### Analytics API
- `POST /api/v1/stochastic/analytics/monte-carlo/start` - Start Monte Carlo
- `GET /api/v1/stochastic/analytics/monte-carlo/{job_id}/status` - Check status
- `POST /api/v1/advanced-analytics/sensitivity-analysis` - Sensitivity analysis
- `POST /api/v1/stochastic/analytics/variability` - Variability metrics

See interactive documentation for complete API reference.
