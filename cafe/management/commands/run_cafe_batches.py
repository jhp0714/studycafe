from django.core.management.base import BaseCommand, CommandError

from cafe.services.batches import run_all_batches, run_auto_checkout, run_expire_passes
from cafe.services.cleanup import run_cleanup_jobs


class Command(BaseCommand):
    help = "스터디카페 배치 실행"

    def add_arguments(self, parser):
        parser.add_argument(
            "--job",
            type=str,
            choices=["all","auto_checkout","expire","cleanup"],
            default="all",
            help="실행할 배치 작업 선택",
        )

    def handle(self, *args, **options):
        job = options["job"]

        try:
            if job == "auto_checkout":
                result = run_auto_checkout()
            elif job == "expire":
                result = run_expire_passes()
            elif job == "cleanup":
                result = run_cleanup_jobs()
            elif job == "all":
                result = run_all_batches()
            else:
                raise CommandError("지원하지 않는 job 입니다.")
        except Exception as e:
            raise CommandError(f"배치 실행 실패:{e}")

        self.stdout.write(self.style.SUCCESS("배치 실행 완료"))
        self.stdout.write(str(result))