#!/bin/bash
# JuryAI Backend - One-shot Docker Compose Startup Script
# Usage: ./start.sh [up|down|logs|restart|status]

set -e

COMPOSE_FILE="docker-compose.yml"
ENV_FILE=".env"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_docker() {
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    if ! command -v docker compose &> /dev/null; then
        log_error "Docker Compose is not installed. Please install Docker Compose v2."
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        log_error "Docker daemon is not running. Please start Docker."
        exit 1
    fi
}

check_env() {
    if [ ! -f "$ENV_FILE" ]; then
        log_warning "No .env file found. Copying from .env.example..."
        if [ -f ".env.example" ]; then
            cp .env.example .env
            log_warning "Please edit .env with your API keys and configuration, then run again."
            exit 1
        else
            log_error "No .env.example found. Cannot create .env file."
            exit 1
        fi
    fi
}

cmd_up() {
    log_info "Starting JuryAI backend services..."
    check_env
    
    log_info "Pulling latest images..."
    docker compose -f "$COMPOSE_FILE" pull
    
    log_info "Building backend image..."
    docker compose -f "$COMPOSE_FILE" build backend
    
    log_info "Starting all services..."
    docker compose -f "$COMPOSE_FILE" up -d
    
    log_info "Waiting for services to be healthy..."
    sleep 10
    
    # Wait for health checks
    local max_wait=180
    local waited=0
    while [ $waited -lt $max_wait ]; do
        if docker compose -f "$COMPOSE_FILE" ps | grep -q "unhealthy"; then
            log_error "Some services are unhealthy. Check logs with: $0 logs"
            docker compose -f "$COMPOSE_FILE" ps
            exit 1
        fi
        
        if docker compose -f "$COMPOSE_FILE" ps | grep -q "starting"; then
            sleep 5
            waited=$((waited + 5))
            continue
        fi
        
        # All services should be running
        local running=$(docker compose -f "$COMPOSE_FILE" ps --services --filter "status=running" | wc -l)
        local total=$(docker compose -f "$COMPOSE_FILE" ps --services | wc -l)
        
        if [ "$running" -eq "$total" ]; then
            log_success "All services are running!"
            break
        fi
        
        sleep 5
        waited=$((waited + 5))
    done
    
    if [ $waited -ge $max_wait ]; then
        log_warning "Timeout waiting for services. Check status with: $0 status"
    fi
    
    cmd_status
}

cmd_down() {
    log_info "Stopping all services..."
    docker compose -f "$COMPOSE_FILE" down
    log_success "All services stopped."
}

cmd_logs() {
    local service=${1:-}
    if [ -n "$service" ]; then
        docker compose -f "$COMPOSE_FILE" logs -f "$service"
    else
        docker compose -f "$COMPOSE_FILE" logs -f
    fi
}

cmd_restart() {
    local service=${1:-}
    if [ -n "$service" ]; then
        log_info "Restarting service: $service"
        docker compose -f "$COMPOSE_FILE" restart "$service"
    else
        log_info "Restarting all services..."
        docker compose -f "$COMPOSE_FILE" restart
    fi
    log_success "Restart complete."
}

cmd_status() {
    log_info "Service Status:"
    docker compose -f "$COMPOSE_FILE" ps
    echo ""
    log_info "Resource Usage:"
    docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}" $(docker compose -f "$COMPOSE_FILE" ps -q) 2>/dev/null || true
}

cmd_build() {
    log_info "Building backend image..."
    docker compose -f "$COMPOSE_FILE" build --no-cache backend
    log_success "Build complete."
}

cmd_pull() {
    log_info "Pulling latest images..."
    docker compose -f "$COMPOSE_FILE" pull
    log_success "Pull complete."
}

cmd_clean() {
    log_warning "This will remove all containers, volumes, and networks!"
    read -p "Are you sure? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker compose -f "$COMPOSE_FILE" down -v --remove-orphans
        docker system prune -f
        log_success "Cleanup complete."
    else
        log_info "Cleanup cancelled."
    fi
}

# Main command dispatch
case "${1:-up}" in
    up|start)
        cmd_up
        ;;
    down|stop)
        cmd_down
        ;;
    logs)
        cmd_logs "$2"
        ;;
    restart)
        cmd_restart "$2"
        ;;
    status|ps)
        cmd_status
        ;;
    build)
        cmd_build
        ;;
    pull)
        cmd_pull
        ;;
    clean)
        cmd_clean
        ;;
    *)
        echo "Usage: $0 {up|down|logs|restart|status|build|pull|clean}"
        echo ""
        echo "Commands:"
        echo "  up/start    - Start all services (default)"
        echo "  down/stop   - Stop all services"
        echo "  logs [svc]  - Follow logs (optionally for specific service)"
        echo "  restart [svc]- Restart all services or specific service"
        echo "  status/ps   - Show service status and resource usage"
        echo "  build       - Rebuild backend image"
        echo "  pull        - Pull latest base images"
        echo "  clean       - Remove all containers, volumes, networks"
        exit 1
        ;;
esac