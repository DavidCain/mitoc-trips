const BundleTracker = require("webpack-bundle-tracker");

module.exports = {
  lintOnSave: false,
  // Include the full runtime compiler, which will allow us to parse outerHTML
  // (Which is necessary on our entrypoint #root, where we read server-generated HTML)
  // See:
  // - https://vuejs.org/v2/guide/instance.html#Lifecycle-Diagram
  // - https://vuejs.org/v2/guide/installation.html#Runtime-Compiler-vs-Runtime-only
  runtimeCompiler: true,

  publicPath: "http://0.0.0.0:8080/",
  outputDir: "./dist/",
  chainWebpack: config => {
    config.optimization.splitChunks(false);
    config
      .plugin("BundleTracker")
      .use(BundleTracker, [{ filename: "../frontend/webpack-stats.json" }]);
    config.resolve.alias.set("__STATIC__", "static");
    config.devServer
      .public("http://0.0.0.0:8080")
      .host("0.0.0.0")
      .port(8080)
      .hotOnly(true)
      .watchOptions({ poll: 1000 })
      .https(false)
      .headers({ "Access-Control-Allow-Origin": ["*"] });
  }
};
