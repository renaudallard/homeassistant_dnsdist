import resolve from '@rollup/plugin-node-resolve';
import typescript from '@rollup/plugin-typescript';
import terser from '@rollup/plugin-terser';

export default {
  input: 'src/dnsdist-card.ts',
  output: {
    file: '../www/dnsdist-card.js',
    format: 'es',
    sourcemap: false,
  },
  plugins: [
    resolve(),
    typescript({
      tsconfig: './tsconfig.json',
      declaration: false,
      noEmit: false,
    }),
    terser({
      format: {
        comments: false,
      },
    }),
  ],
};
