# Асинхронный анализ vs последовательный

В первом задании при распараллеливании мы выполняли анализ дольше. Это связано с тем, что создание нового процесса требует ресурсов, и при малом количестве данных расходы на распараллеливание не окупаются. Также в колабе число ядер ограничено, что не позволяет использовать распараллеливание на полную.

Когда мы во втором задании выполняли запросы к API, асинхронный метод логично оказался значительно быстрее.