package android.util

/**
 * Mock implementation of android.util.Log for unit tests.
 * Simply prints to stdout for debugging.
 */
object Log {
    @JvmStatic
    fun d(tag: String?, msg: String?): Int {
        println("D/$tag: $msg")
        return 0
    }

    @JvmStatic
    fun i(tag: String?, msg: String?): Int {
        println("I/$tag: $msg")
        return 0
    }

    @JvmStatic
    fun w(tag: String?, msg: String?): Int {
        println("W/$tag: $msg")
        return 0
    }

    @JvmStatic
    fun w(tag: String?, msg: String?, tr: Throwable?): Int {
        println("W/$tag: $msg")
        tr?.printStackTrace()
        return 0
    }

    @JvmStatic
    fun e(tag: String?, msg: String?): Int {
        println("E/$tag: $msg")
        return 0
    }

    @JvmStatic
    fun e(tag: String?, msg: String?, tr: Throwable?): Int {
        println("E/$tag: $msg")
        tr?.printStackTrace()
        return 0
    }

    @JvmStatic
    fun v(tag: String?, msg: String?): Int {
        println("V/$tag: $msg")
        return 0
    }

    @JvmStatic
    fun wtf(tag: String?, msg: String?): Int {
        println("WTF/$tag: $msg")
        return 0
    }
}
