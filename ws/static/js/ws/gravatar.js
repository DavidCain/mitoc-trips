angular.module('ui.gravatar').config([
  'gravatarServiceProvider', function(gravatarServiceProvider) {
    // Set defaults to mirror Gravatar template tags in Django
    gravatarServiceProvider.defaults = {
      size: 40,
      r: 'pg',
      "default": 'mm',  // Mystery man as default for missing avatars
    };

    // Use HTTPS endpoint
    gravatarServiceProvider.secure = true;
  }
]);
