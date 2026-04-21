from django.core.management.base import BaseCommand

from cafe.models import Seat, Locker

class Command(BaseCommand):
    help = "일반석 60개, 지정석 20개, 사물함 40개 생성"

    def handle(self, *args, **options):
        normal_seats = [
            Seat(
                seat_no=f"N{i:02d}",
                seat_type=Seat.SeatType.NORMAL,
                available=True,
            )
            for i in range(1, 61)
        ]

        fixed_seats = [
            Seat(
                seat_no=f"F{i:02d}",
                seat_type=Seat.SeatType.FIXED,
                available=True,
            )
            for i in range(1, 21)
        ]

        lockers = [
            Locker(
                locker_no=f"L{i:02d}",
                available=True,
            )
            for i in range(1, 41)
        ]

        Seat.objects.bulk_create(normal_seats, ignore_conflicts=True)
        Seat.objects.bulk_create(fixed_seats, ignore_conflicts=True)
        Locker.objects.bulk_create(lockers, ignore_conflicts=True)

        self.stdout.write(self.style.SUCCESS("기본 좌석/사물함 데이터 생성 완료"))