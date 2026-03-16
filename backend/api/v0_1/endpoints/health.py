"""
Health check and environment validation endpoints.
"""

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# AgentFactory import removed - not used in health checks


logger = logging.getLogger('app')

router = APIRouter(prefix="/health", tags=["Health & Monitoring"])


class HealthStatus(BaseModel):
    """Health check response model."""
    status: str
    timestamp: datetime
    version: str = "0.1.0"
    checks: Dict[str, Any] = {}


class ValidationResult(BaseModel):
    """Environment validation result model."""
    valid: bool
    checks: List[Dict[str, Any]]
    timestamp: datetime


@router.get("/", response_model=HealthStatus)
@router.get("", response_model=HealthStatus)
async def health_check():
    """
    Basic health check endpoint.
    
    Returns:
    - **status**: overall health status (healthy/unhealthy)
    - **timestamp**: current timestamp
    - **version**: application version
    - **checks**: detailed check results
    """
    try:
        checks = {}
        
        # Basic application health
        checks["application"] = {
            "status": "healthy",
            "message": "Application is running"
        }
        
        # Environment variables check
        required_env_vars = [
            "ROOT_DIRECTORY",
            "ENFORCER_MODEL",
            "ENFORCER_POLICY"
        ]
        
        missing_vars = [var for var in required_env_vars if not os.getenv(var)]
        if missing_vars:
            checks["environment"] = {
                "status": "warning",
                "message": f"Missing environment variables: {', '.join(missing_vars)}"
            }
        else:
            checks["environment"] = {
                "status": "healthy",
                "message": "All required environment variables present"
            }
        
        # Determine overall status
        overall_status = "healthy"
        if any(check.get("status") == "unhealthy" for check in checks.values()):
            overall_status = "unhealthy"
        elif any(check.get("status") == "warning" for check in checks.values()):
            overall_status = "warning"
        
        return HealthStatus(
            status=overall_status,
            timestamp=datetime.now(timezone.utc),
            checks=checks
        )
    
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return HealthStatus(
            status="unhealthy",
            timestamp=datetime.now(timezone.utc),
            checks={
                "error": {
                    "status": "unhealthy",
                    "message": f"Health check failed: {str(e)}"
                }
            }
        )


@router.get("/detailed", response_model=HealthStatus)
async def detailed_health_check():
    """
    Detailed health check including external dependencies.
    
    Checks:
    - Application status
    - Environment configuration
    - File system access
    - Keycloak connectivity (if configured)
    """
    try:
        checks = {}
        
        # Basic application health
        checks["application"] = {
            "status": "healthy",
            "message": "Application is running"
        }
        
        # Environment variables
        required_env_vars = [
            "ROOT_DIRECTORY", "ENFORCER_MODEL", "ENFORCER_POLICY",
            "INSTANCE_CONFIGS"
        ]
        
        missing_vars = [var for var in required_env_vars if not os.getenv(var)]
        if missing_vars:
            checks["environment"] = {
                "status": "unhealthy",
                "message": f"Missing critical environment variables: {', '.join(missing_vars)}"
            }
        else:
            checks["environment"] = {
                "status": "healthy",
                "message": "Environment variables configured"
            }
        
        # File system access
        try:
            root_dir = os.getenv('ROOT_DIRECTORY')
            if root_dir and Path(root_dir).exists() and os.access(root_dir, os.R_OK):
                checks["filesystem"] = {
                    "status": "healthy",
                    "message": "File system accessible"
                }
            else:
                checks["filesystem"] = {
                    "status": "unhealthy", 
                    "message": "Root directory not accessible"
                }
        except Exception as e:
            checks["filesystem"] = {
                "status": "unhealthy",
                "message": f"File system check failed: {str(e)}"
            }
        
        # Keycloak connectivity
        try:
            keycloak_domain = os.getenv('KEYCLOAK_DOMAIN')
            if keycloak_domain:
                # Basic connectivity check (would need actual implementation)
                checks["keycloak"] = {
                    "status": "unknown",
                    "message": f"Keycloak configured at {keycloak_domain} (connectivity not tested)"
                }
            else:
                checks["keycloak"] = {
                    "status": "warning",
                    "message": "Keycloak not configured"
                }
        except Exception as e:
            checks["keycloak"] = {
                "status": "unhealthy",
                "message": f"Keycloak check failed: {str(e)}"
            }
        
        # Determine overall status
        overall_status = "healthy"
        if any(check.get("status") == "unhealthy" for check in checks.values()):
            overall_status = "unhealthy"
        elif any(check.get("status") in ["warning", "unknown"] for check in checks.values()):
            overall_status = "warning"
        
        return HealthStatus(
            status=overall_status,
            timestamp=datetime.now(timezone.utc),
            checks=checks
        )
    
    except Exception as e:
        logger.error(f"Detailed health check failed: {str(e)}")
        return HealthStatus(
            status="unhealthy",
            timestamp=datetime.now(timezone.utc),
            checks={
                "error": {
                    "status": "unhealthy",
                    "message": f"Health check failed: {str(e)}"
                }
            }
        )


@router.get("/validate", response_model=ValidationResult)
async def validate_environment():
    """
    Comprehensive environment validation.
    
    Validates:
    - Configuration files exist and are readable
    - Required directories exist with proper permissions
    - Secrets are properly configured
    - Storage instances can be initialized
    """
    checks = []
    overall_valid = True
    
    try:
        # Configuration files validation
        config_files = [
            ("Main config", "config.yaml"),
            ("Environment config", "core/settings/.env"),
            ("Secrets file", "core/settings/security/.secrets"),
            ("Logging config", os.getenv('LOG_CONFIG', 'loggers/log_config.yaml'))
        ]
        
        for name, file_path in config_files:
            if not file_path:
                checks.append({
                    "check": name,
                    "status": "fail",
                    "message": "Path not configured"
                })
                overall_valid = False
                continue
                
            full_path = Path(os.getenv('ROOT_DIRECTORY', '')) / file_path
            if full_path.exists() and os.access(full_path, os.R_OK):
                checks.append({
                    "check": name,
                    "status": "pass",
                    "message": f"File exists and is readable: {file_path}"
                })
            else:
                checks.append({
                    "check": name,
                    "status": "fail", 
                    "message": f"File missing or not readable: {file_path}"
                })
                overall_valid = False
        
        # Directory permissions
        directories = [
            ("instance configs", os.getenv('INSTANCE_CONFIGS')),
            ("Logs", "loggers/logs")
        ]
        
        for name, dir_path in directories:
            if not dir_path:
                checks.append({
                    "check": f"{name} directory",
                    "status": "fail",
                    "message": "Directory path not configured"
                })
                overall_valid = False
                continue
            
            full_path = Path(os.getenv('ROOT_DIRECTORY', '')) / dir_path
            if full_path.exists() and os.access(full_path, os.R_OK):
                checks.append({
                    "check": f"{name} directory",
                    "status": "pass",
                    "message": f"Directory accessible: {dir_path}"
                })
            else:
                checks.append({
                    "check": f"{name} directory",
                    "status": "fail",
                    "message": f"Directory missing or not accessible: {dir_path}"
                })
                overall_valid = False
        
        # Secrets validation
        secrets_file = Path(os.getenv('ROOT_DIRECTORY', '')) / 'core/settings/security/.secrets'
        
        if secrets_file.exists():
            try:
                with open(secrets_file, 'r') as f:
                    content = f.read()
                    if 'REPLACE_WITH_GENERATED_VALUE' in content:
                        checks.append({
                            "check": "Secrets generation",
                            "status": "fail",
                            "message": "Secrets contain template values - regenerate secrets"
                        })
                        overall_valid = False
                    else:
                        checks.append({
                            "check": "Secrets generation", 
                            "status": "pass",
                            "message": "Secrets have been generated"
                        })
            except Exception as e:
                checks.append({
                    "check": "Secrets validation",
                    "status": "fail",
                    "message": f"Failed to read secrets file: {str(e)}"
                })
                overall_valid = False
        
        # Environment variables
        critical_env_vars = [
            "ROOT_DIRECTORY", "ENFORCER_MODEL", "ENFORCER_POLICY",
            "INSTANCE_CONFIGS"
        ]
        
        missing_vars = [var for var in critical_env_vars if not os.getenv(var)]
        if missing_vars:
            checks.append({
                "check": "Environment variables",
                "status": "fail",
                "message": f"Missing critical variables: {', '.join(missing_vars)}"
            })
            overall_valid = False
        else:
            checks.append({
                "check": "Environment variables",
                "status": "pass", 
                "message": "All critical environment variables present"
            })
    
    except Exception as e:
        logger.error(f"Environment validation failed: {str(e)}")
        checks.append({
            "check": "Validation process",
            "status": "fail",
            "message": f"Validation failed with error: {str(e)}"
        })
        overall_valid = False
    
    return ValidationResult(
        valid=overall_valid,
        checks=checks,
        timestamp=datetime.now(timezone.utc)
    )


@router.get("/ready")
async def readiness_check():
    """
    Kubernetes-style readiness probe.
    
    Returns HTTP 200 if the application is ready to serve traffic,
    HTTP 503 if not ready.
    """
    try:
        # Check critical components
        if not os.getenv('ROOT_DIRECTORY'):
            logger.error("Readiness check failed: Root directory not configured")
            raise HTTPException(status_code=503, detail="Root directory not configured")
        
        if not os.getenv('ENFORCER_MODEL'):
            logger.error("Readiness check failed: Policy engine not configured")
            raise HTTPException(status_code=503, detail="Policy engine not configured")
        
        return {"status": "ready", "timestamp": datetime.now(timezone.utc)}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Readiness check failed: {str(e)}")
        raise HTTPException(status_code=503, detail=f"Not ready: {str(e)}")


@router.get("/live")
async def liveness_check():
    """
    Kubernetes-style liveness probe.
    
    Returns HTTP 200 if the application is running,
    HTTP 503 if it should be restarted.
    """
    try:
        # Basic application liveness - if this endpoint responds, we're alive
        return {"status": "alive", "timestamp": datetime.now(timezone.utc)}
    
    except Exception as e:
        logger.error(f"Liveness check failed: {str(e)}")
        raise HTTPException(status_code=503, detail=f"Not alive: {str(e)}")