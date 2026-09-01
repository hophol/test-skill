module.exports = {
  testEnvironment: 'jsdom',
  transform: { '^.+\\.[jt]sx?$': ['babel-jest', { configFile: './babel.config.cjs' }] },
  testMatch: ['**/*.test.{js,jsx,ts,tsx}'],
};
