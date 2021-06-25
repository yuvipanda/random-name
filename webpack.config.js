const webpack = require('webpack');
const path = require('path');

const MiniCssExtractPlugin = require('mini-css-extract-plugin');

module.exports = {
    mode: 'production',
    context: path.resolve(__dirname, 'binderhub/static'),
    entry: "./js/index.js",
    output: {
        path: path.resolve(__dirname, 'binderhub/static/dist/'),
        filename: "bundle.js",
        publicPath: '/static/dist/'
    },
    plugins: [
        new webpack.ProvidePlugin({
            $: 'jquery',
            jQuery: 'jquery',
        }),
        new MiniCssExtractPlugin({
            filename: 'styles.css'
        }),
    ],
    module: {
        rules: [
            {
                test: /\.css$/i,
                use: [
                    {
                        loader: MiniCssExtractPlugin.loader,
                        options: {
                            // Set publicPath as relative path ("./").
                            // By default it uses the `output.publicPath` ("/static/dist/"), when it rewrites the URLs in styles.css.
                            // And it causes these files unavailabe if BinderHub has a different base_url than "/".
                            publicPath: "./",
                        },
                    },
                    'css-loader'
                ],
            },
            {
                test: /\.(eot|woff|ttf|woff2|svg)$/,
                type: 'asset/resource'
            }
        ]
    },
    devtool: 'source-map',
}
