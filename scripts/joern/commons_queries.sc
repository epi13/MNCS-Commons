import io.shiftleft.semanticcpg.language.*

val targets = List("validate_record", "validate_event", "validate_transition", "derive_lifecycle", "add_record", "add_event", "verify", "query", "main", "load_document")
println("METHOD_COUNT=" + cpg.method.name.l.filter(targets.contains).size)
targets.foreach { name =>
  val methods = cpg.method.l.filter(_.name == name)
  val callers = methods.flatMap(_.callIn.method.name.l).distinct.sorted.mkString(",")
  val controls = methods.flatMap(_.controlStructure.controlStructureType.l).groupBy(identity).view.mapValues(_.size).toSeq.sortBy(_._1).mkString(",")
  println(s"METHOD|$name|count=${methods.size}|callers=$callers|controls=$controls")
}
val dangerous = Set("system", "popen", "run", "Popen", "exec", "eval", "shell")
println("DANGEROUS_CALL_NAMES=" + cpg.call.name.l.filter(dangerous.contains).distinct.sorted.mkString(","))
println("CONTROL_STRUCTURES=" + cpg.controlStructure.size)
