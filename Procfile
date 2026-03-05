web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
worker: rq worker --url $REDIS_URL email-reviewer
