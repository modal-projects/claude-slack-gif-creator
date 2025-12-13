import os

import modal

proxy_image =  modal.Image.debian_slim(python_version="3.12").pip_install("httpx", "fastapi")

anthropic_secret = modal.Secret.from_name("anthropic-secret")  # ANTHROPIC_API_KEY

app = modal.App("slack-gif-creator-anthropic-proxy")

@app.function(secrets=[anthropic_secret], image=proxy_image, region="us-east-1", min_containers=1)
@modal.concurrent(max_inputs=100)
@modal.asgi_app()
def anthropic_proxy():
    import httpx
    from fastapi import FastAPI, HTTPException, Request, Response

    proxy_app = FastAPI()

    @proxy_app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
    async def proxy(request: Request, path: str):
        headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}

        sandbox_id = headers.get("x-api-key")

        try:
            sb = await modal.Sandbox.from_id.aio(sandbox_id)
            if sb.returncode is not None:
                raise HTTPException(status_code=403, detail="Sandbox no longer running")
        except modal.exception.NotFoundError:
            raise HTTPException(status_code=403, detail="Invalid sandbox ID")

        headers["x-api-key"] = os.environ["ANTHROPIC_API_KEY"]

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://api.anthropic.com/{path}",
                headers=headers,
                content=await request.body(),
                timeout=300.0,
            )

        return Response(content=resp.content, status_code=resp.status_code, media_type="application/json")

    return proxy_app
