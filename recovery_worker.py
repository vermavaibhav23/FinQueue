import os

import django


def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'finqueue.settings')
    django.setup()

    from apps.worker.recovery import StaleJobRecoveryWorker

    StaleJobRecoveryWorker().run_forever()


if __name__ == '__main__':
    main()
