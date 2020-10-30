const webpack = require("webpack");
const ExtractTextPlugin = require("extract-text-webpack-plugin");

module.exports = {
  context: __dirname + "/binderhub/static/",
  entry: "./js/index.js",
  output: {
    path: __dirname + "/binderhub/static/dist/",
    filename: "bundle.js",
    publicPath: "/static/dist/"
  },
  module: {
    rules: [
      {
        test: /\.css$/,
        use: ExtractTextPlugin.extract({
          fallback: "style-loader",
          use: "css-loader"
        })
      },
      {
        test: /\.(eot|woff|ttf|woff2|svg)$/,
        loader: "file-loader"
      },
      {
        test: /\.js$/,
        exclude: [/node_modules/, /js\/vendor/],
        use: [{ loader: "babel-loader" }]
      }
    ]
  },
  devtool: "source-map",
  plugins: [
    new webpack.ProvidePlugin({
      $: "jquery",
      jQuery: "jquery"
    }),
    new ExtractTextPlugin("styles.css")
  ]
};
