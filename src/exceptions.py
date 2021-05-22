class BaseTrackerError(Exception):
    pass


class BaseWrongArgumentError(BaseTrackerError):
    pass


class BaseNotFoundError(BaseTrackerError):
    pass


# ------ tracker errors -----
class MaterialEvenCompleted(BaseTrackerError):
    pass


class MaterialNotAssigned(BaseTrackerError):
    pass


class DatabaseError(BaseTrackerError):
    pass


# ------ invalid argument errors -----
class WrongDate(BaseWrongArgumentError):
    pass


class WrongRepeatResult(BaseWrongArgumentError):
    pass


# ------ not found errors -----
class MaterialNotFound(BaseNotFoundError):
    pass


class CardNotFound(BaseNotFoundError):
    pass

