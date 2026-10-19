from rest_framework.throttling import ScopedRateThrottle


class LoginThrottle(ScopedRateThrottle):
    scope = "login"


class SignupThrottle(ScopedRateThrottle):
    scope = "signup"


class KarzaiThrottle(ScopedRateThrottle):
    scope = "karzai"


class KycReviewThrottle(ScopedRateThrottle):
    scope = "kyc_review"
