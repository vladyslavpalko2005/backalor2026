"""Single cloud API process; PostgreSQL credentials never reach the desktop client."""
import os
import uvicorn


def main():
    port=int(os.getenv('PORT','8000'))
    if not 1<=port<=65535:raise ValueError('PORT must be 1–65535')
    uvicorn.run('backend.main:create_app',factory=True,host='0.0.0.0',port=port,
                workers=1,access_log=False,proxy_headers=False)


if __name__=='__main__':main()
