import Vue from "vue";

function baseComponentsRequireContext(): __WebpackModuleApi.RequireContext {
  return require.context(
    "./components",
    // Do not look in subfolders
    false,
    // For now, we will export _all_ top-level components for use in DOM templates.
    // This differs a bit from Vue convention: https://vuejs.org/v2/style-guide/#Base-component-names-strongly-recommended
    /[A-Z]\w+\.vue$/
  );
}

export function pathToComponentName(componentPath: string): string {
  const filename = componentPath.split("/").pop() || componentPath;
  return filename.replace(/\.vue$/, "");
}

/**
 * Automatically register all base components for use in DOM templates.
 *
 * This helps avoid the issue of accidentally forgetting to specify a component in main.ts
 *
 * Importantly, this *must* be invoked before the Vue instance is initialized.
 */
export default function registerBaseComponents(): void {
  const requireComponent = baseComponentsRequireContext();
  requireComponent.keys().forEach(filename => {
    const componentConfig = requireComponent(filename);
    const componentName = pathToComponentName(filename);

    Vue.component(
      componentName,
      // We mandate an `export default` on each base component
      // (though we could fall back to the module's root if desired)
      componentConfig.default
    );
  });
}
