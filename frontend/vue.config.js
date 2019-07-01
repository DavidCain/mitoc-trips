module.exports = {
  // Include the full runtime compiler, which will allow us to parse outerHTML
  // (Which is necessary on our entrypoint #root, where we read server-generated HTML)
  // See:
  // - https://vuejs.org/v2/guide/instance.html#Lifecycle-Diagram
  // - https://vuejs.org/v2/guide/installation.html#Runtime-Compiler-vs-Runtime-only
  runtimeCompiler: true,
  lintOnSave: false
};
