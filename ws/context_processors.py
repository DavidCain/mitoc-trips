def get_groups(request):
    group_names = [group.name for group in request.user.groups.all()]
    return {'groups': group_names}
