from slowapi import Limiter

from app.core.security.network import client_ip

# Los contadores viven en memoria: vale mientras el backend corra con una sola réplica.
limiter = Limiter(key_func=client_ip)
