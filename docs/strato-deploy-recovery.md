# STRATO deployment recovery

The deployment workflow removes stale temporary Docker Compose recreate containers before starting a new release. Persistent application data and normal service containers are not targeted by that cleanup.

Full releases now wait for stateless application containers to finish removal before Compose recreates them. PostgreSQL, Redis and persistent volumes are excluded from this cleanup.
