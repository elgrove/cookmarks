package com.cookmarks.app

import com.cookmarks.app.ui.Feedback
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Test

class FeedbackTest {
    @Test
    fun feedback_show_emits_message_to_flow() = runBlocking {
        Feedback.show("Test error message")
        val received = Feedback.messages.first()
        assertEquals("Test error message", received)
    }
}
