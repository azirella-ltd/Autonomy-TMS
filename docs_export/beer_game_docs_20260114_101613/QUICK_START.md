# Quick Start Guide

## 1. Installation

### Prerequisites
- Docker 20.10+
- Docker Compose 2.0+
- 8GB RAM minimum
- 20GB disk space

### Setup
```bash
# Clone repository
git clone <repository-url>
cd The_Beer_Game

# Initialize environment
make init-env

# Start application
make up

# Bootstrap database
make db-bootstrap
```

## 2. Access Application

- **Frontend**: http://localhost:8088
- **API Docs**: http://localhost:8000/docs
- **Admin Panel**: http://localhost:8080

### Default Credentials
- Email: systemadmin@autonomy.ai
- Password: Autonomy@2025

## 3. Create Your First Game

### Option 1: Quick Start Wizard (Recommended)
1. Log in to the application
2. Click "Create New Game"
3. Select "Quick Start Wizard"
4. Choose industry and difficulty
5. Select recommended template
6. Launch game

### Option 2: Manual Configuration
1. Log in to the application
2. Navigate to "Supply Chain Configs"
3. Select or create a configuration
4. Create new game with selected config
5. Add players (human or AI)
6. Start game

## 4. Run a Simulation

1. Create game with AI agents
2. Start game
3. Click "Auto-play" to run simulation
4. View analytics dashboard
5. Export results

## 5. Advanced Features

### Monte Carlo Simulation
1. Create game
2. Navigate to "Stochastic Analytics"
3. Configure Monte Carlo parameters
4. Start simulation (50-1000 runs)
5. Analyze results

### Sensitivity Analysis
1. Run base simulation
2. Navigate to "Advanced Analytics"
3. Select "Sensitivity Analysis"
4. Choose parameters to vary
5. View tornado diagrams

## 6. Testing the System

### Run Tests
```bash
# Integration tests
./backend/scripts/run_integration_tests.sh

# Load tests
cd backend/tests/load
locust -f locustfile.py --users 10 --spawn-rate 2

# Health validation
./backend/scripts/validate_health.sh
```

## 7. Next Steps

- Read [DOCUMENTATION_INDEX.md](DOCUMENTATION_INDEX.md) for complete documentation
- Explore [Template Library](http://localhost:8088/templates)
- Try different AI agent strategies
- Configure custom supply chain networks

## Troubleshooting

### Application won't start
```bash
# Check Docker status
docker compose ps

# View logs
make logs

# Restart services
make down && make up
```

### Database connection error
```bash
# Reset database
make db-reset

# Reinitialize
make db-bootstrap
```

### Port already in use
```bash
# Find process using port
lsof -i :8000

# Kill process
kill -9 <PID>
```

For more help, see [Troubleshooting Guide](deployment/DEPLOYMENT.md#troubleshooting).
