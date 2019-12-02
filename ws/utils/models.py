from ws import enums


def problems_with_profile(participant):
    if not participant:
        yield enums.ProfileProblem.NO_INFO
        return

    yield from participant.problems_with_profile
