from django import template

register = template.Library()


@register.inclusion_tag('for_templatetags/cdn_fallback.html')
def cdn_fallback(lib_name, cdn_url, bower_path):
    """ Load the package from a CDN, but fall back to local service on failure. """
    return {'lib_name': lib_name,
            'cdn_url': cdn_url,
            'bower_path': bower_path}
