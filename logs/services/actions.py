class LogAction:
    # 주문 / 결제
    ORDER_CREATED = "order_created"
    PAYMENT_CREATED = "payment_created"
    PAYMENT_PAID = "payment_paid"
    PAYMENT_REFUNDED = "payment_refunded"

    # 패스
    PASS_ISSUED = "pass_issued"
    PASS_EXTENDED = "pass_extended"
    PASS_EXPIRED = "pass_expired"
    PASS_CANCELED = "pass_canceled"

    # 일반석 / 지정석
    SEAT_CHECKED_IN = "seat_checked_in"
    FIXED_SEAT_CHECKED_IN = "fixed_seat_checked_in"
    SEAT_CHECKED_OUT = "seat_checked_out"
    SEAT_AUTO_CHECKED_OUT = "seat_auto_checked_out"
    SEAT_FORCE_CHECKED_OUT = "seat_force_checked_out"
    SEAT_MOVED = "seat_moved"
    SEAT_EXTENDED = "seat_extended"
    FIXED_SEAT_MOVED = "fixed_seat_moved"

    # 사물함
    LOCKER_ASSIGNED = "locker_assigned"
    LOCKER_MOVED = "locker_moved"
    LOCKER_UNASSIGNED = "locker_unassigned"

    # 환불
    REFUND_CREATED = "refund_created"
    REFUND_COMPLETED = "refund_completed"

    # 배치 / 시스템
    BATCH_AUTO_CHECKOUT_RUN = "batch_auto_checkout_run"
    BATCH_PASS_EXPIRE_RUN = "batch_pass_expire_run"
    BATCH_CLEANUP_RUN = "batch_cleanup_run"
    BATCH_ALL_RUN = "batch_all_run"


class LogEntityType:
    ORDER = "order"
    PAYMENT = "payment"
    PASS = "pass"
    SEAT = "seat"
    LOCKER = "locker"
    SEAT_USAGE = "seat_usage"
    LOCKER_USAGE = "locker_usage"
    REFUND = "refund"
    BATCH = "batch"
    PRODUCT = "product"