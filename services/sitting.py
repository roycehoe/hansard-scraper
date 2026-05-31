from database.handsard_sitting_date_response import HandsardSittingDateResponse
from database.sitting import Sitting


def build_sitting(response: HandsardSittingDateResponse) -> Sitting:
    return Sitting(**response.model_dump(exclude={"id"}))
