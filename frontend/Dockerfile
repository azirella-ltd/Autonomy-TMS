# Build stage
FROM node:18-alpine AS build

WORKDIR /app

# Install system dependencies for native modules
RUN apk add --no-cache python3 make g++

# Copy package files and install TypeScript
COPY package*.json ./
RUN npm install -g typescript

# Install all dependencies including peer dependencies
RUN npm install --legacy-peer-deps

# Install additional required dependencies
RUN npm install formik yup @hookform/resolvers react-hook-form

# Copy TypeScript config
COPY tsconfig.json ./

# Copy environment configuration
COPY .env* ./

# Copy the rest of the application
COPY . .

# Set environment to production and configure default API base URLs. These can be overridden
# via --build-arg when invoking docker build / compose.
ARG REACT_APP_API_BASE_URL=/api/v1
ARG VITE_API_BASE_URL=/api/v1

ENV NODE_ENV=production \
    REACT_APP_API_BASE_URL=${REACT_APP_API_BASE_URL} \
    VITE_API_BASE_URL=${VITE_API_BASE_URL}

# Build the application
RUN echo "Building with API_BASE_URL: ${REACT_APP_API_BASE_URL:-http://localhost:8000/api/v1}" && \
    npm run build

# Remove development dependencies after build
RUN npm prune --production

# Production stage
FROM nginx:alpine

# Install wget for healthcheck
RUN apk add --no-cache wget

# Copy built assets from the build stage
COPY --from=build /app/build /usr/share/nginx/html

# Copy nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Set proper permissions
RUN chmod -R 755 /usr/share/nginx/html && \
    chmod 644 /etc/nginx/conf.d/default.conf && \
    chown -R nginx:nginx /usr/share/nginx/html && \
    chown -R nginx:nginx /var/cache/nginx && \
    chown -R nginx:nginx /var/log/nginx && \
    chown -R nginx:nginx /etc/nginx/conf.d

# Fix permissions
RUN touch /var/run/nginx.pid && \
    chown -R nginx:nginx /var/run/nginx.pid && \
    chmod -R 755 /var/log/nginx && \
    chmod -R 755 /var/cache/nginx

# Run as root to avoid permission issues with nginx
# USER nginx

# Expose port 80
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 CMD wget --no-verbose --tries=1 --spider http://localhost/ || exit 1

# Start Nginx server
CMD ["nginx", "-g", "daemon off;"]
