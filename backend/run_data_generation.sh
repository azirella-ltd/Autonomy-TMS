#!/bin/bash

# Set database environment variables
export MYSQL_USER=autonomy_user
export MYSQL_PASSWORD=Autonomy@2026
export MYSQL_HOST=db
export MYSQL_DB=autonomy

# Activate virtual environment
source venv/bin/activate

# Run the data generation script
python -m app.data.generate_training_data

echo "Data generation complete!"
