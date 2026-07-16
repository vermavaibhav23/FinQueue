import os

import django


def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'finqueue.settings')
    django.setup()

    from apps.worker.engine import WorkerEngine
    from apps.worker.recovery import recover_pending_jobs

    recover_pending_jobs()
    WorkerEngine().run_forever()


if __name__ == '__main__':
    main()
